(function () {
    "use strict";

    const FORMAT_VERSION = 8;
    const DB_VERSION = 1;
    const INDEX_FIELDS = ["title", "content", "source", "tags"];
    const TOKEN_PATTERN = /[\p{L}\p{N}_+#.-]+/gu;
    const RESULT_LIMIT = 1000;
    const TERM_SCAN_LIMIT = 5000;
    const UTF8_DECODER = new TextDecoder();
    const OPEN_DATABASES = new Set();

    function requestResult(request) {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    function transactionDone(transaction) {
        return new Promise((resolve, reject) => {
            transaction.oncomplete = resolve;
            transaction.onabort = transaction.onerror = () => reject(transaction.error);
        });
    }

    function terms(value) {
        return String(value || "")
            .normalize("NFKC")
            .toLocaleLowerCase()
            .match(TOKEN_PATTERN) || [];
    }

    function decodeBase64(value) {
        const padded = value + "=".repeat((4 - value.length % 4) % 4);
        const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
        return Uint8Array.from(binary, (character) => character.charCodeAt(0));
    }

    function readVarint(bytes, state) {
        let value = 0;
        let shift = 0;
        while (state.offset < bytes.length) {
            const byte = bytes[state.offset++];
            value |= (byte & 0x7f) << shift;
            if (!(byte & 0x80)) return value;
            shift += 7;
        }
        throw new Error("Invalid route data");
    }

    function decodePostings(bytes, fields, chunkCount) {
        const state = { offset: 0 };
        const postings = {};
        while (state.offset < bytes.length) {
            const header = readVarint(bytes, state);
            const complement = Boolean(header & 1);
            const fieldMask = header >> 1;
            let chunk = 0;
            const values = [];
            while (state.offset < bytes.length && bytes[state.offset] !== 0) {
                chunk += readVarint(bytes, state) - 1;
                values.push(chunk);
            }
            state.offset += 1;
            const excluded = new Set(values);
            const chunks = complement
                ? Array.from({ length: chunkCount }, (_, index) => index)
                    .filter((index) => !excluded.has(index))
                : values;
            fields.forEach((field, index) => {
                if (fieldMask & (1 << index)) postings[field] = chunks;
            });
        }
        return postings;
    }

    function decodeRoute(value, fields, chunkCount) {
        const bytes = decodeBase64(value);
        const state = { offset: 0 };
        let previous = new Uint8Array();
        const result = [];
        while (state.offset < bytes.length) {
            const shared = readVarint(bytes, state);
            const suffixLength = readVarint(bytes, state);
            const termBytes = new Uint8Array(shared + suffixLength);
            termBytes.set(previous.slice(0, shared));
            termBytes.set(
                bytes.slice(state.offset, state.offset + suffixLength),
                shared,
            );
            state.offset += suffixLength;
            const postingLength = readVarint(bytes, state);
            const postingBytes = bytes.slice(
                state.offset,
                state.offset + postingLength,
            );
            state.offset += postingLength;
            result.push([
                UTF8_DECODER.decode(termBytes),
                decodePostings(postingBytes, fields, chunkCount),
            ]);
            previous = termBytes;
        }
        return result;
    }

    function union(left, right) {
        const result = new Set(left);
        right.forEach((value) => result.add(value));
        return result;
    }

    function intersect(left, right) {
        if (left === null) return new Set(right);
        const result = new Set();
        left.forEach((value) => {
            if (right.has(value)) result.add(value);
        });
        return result;
    }

    class StaticSearchCollection {
        constructor(manifestUrl) {
            this.manifestUrl = new URL(manifestUrl, document.baseURI);
            this.manifestPromise = null;
            this.dbPromise = null;
            this.preparedKey = "";
            this.payloadPromises = new Map();
            this.routePromises = new Map();
            this.chunkPromises = new Map();
            this.syncPromises = new Map();
        }

        async manifest() {
            if (!this.manifestPromise) {
                this.manifestPromise = fetch(this.manifestUrl, { cache: "no-cache" })
                    .then((response) => {
                        if (!response.ok) {
                            throw new Error(`Unable to load ${this.manifestUrl}`);
                        }
                        return response.json();
                    })
                    .then(async (manifest) => {
                        if (manifest.version !== FORMAT_VERSION) {
                            throw new Error("Unsupported search data format");
                        }
                        await this.open(manifest);
                        await this.ensureSynchronized(manifest);
                        const keep = [
                            "index.json",
                            ...new Set([
                                ...manifest.chunks.map((chunk) => chunk.file),
                                ...manifest.routes.map((route) => route.file),
                            ]),
                        ];
                        navigator.serviceWorker?.controller?.postMessage({
                            type: "prune-directory-data",
                            base: new URL(".", this.manifestUrl).href,
                            keep,
                        });
                        return manifest;
                    })
                    .catch((error) => {
                        this.manifestPromise = null;
                        throw error;
                    });
            }
            return this.manifestPromise;
        }

        refresh() {
            this.manifestPromise = null;
            this.preparedKey = "";
            this.routePromises.clear();
            return this.manifest();
        }

        async database(manifest) {
            if (!this.dbPromise) {
                this.dbPromise = new Promise((resolve, reject) => {
                    const request = indexedDB.open(
                        `cpp-social-search-v8:${manifest.collection}`,
                        DB_VERSION,
                    );
                    request.onupgradeneeded = () => {
                        const db = request.result;
                        const records = db.createObjectStore("records", { keyPath: "id" });
                        for (const field of INDEX_FIELDS) {
                            records.createIndex(field, `_terms.${field}`, {
                                multiEntry: true,
                            });
                        }
                        records.createIndex("published", "published");
                        db.createObjectStore("tombstones", { keyPath: "id" });
                        db.createObjectStore("chunks", { keyPath: "id" });
                        db.createObjectStore("routes", { keyPath: "id" });
                        db.createObjectStore("meta", { keyPath: "key" });
                    };
                    request.onsuccess = () => {
                        const db = request.result;
                        OPEN_DATABASES.add(db);
                        db.onversionchange = () => {
                            OPEN_DATABASES.delete(db);
                            db.close();
                        };
                        resolve(db);
                    };
                    request.onerror = () => reject(request.error);
                });
            }
            return this.dbPromise;
        }

        async open(manifest) {
            const db = await this.database(manifest);
            const key = `${manifest.epoch}:${manifest.revision}`;
            if (this.preparedKey === key) return db;

            const transaction = db.transaction(
                ["records", "tombstones", "chunks", "routes", "meta"],
                "readwrite",
            );
            const meta = transaction.objectStore("meta");
            const current = await requestResult(meta.get("epoch"));
            if (current && current.value !== manifest.epoch) {
                transaction.objectStore("records").clear();
                transaction.objectStore("tombstones").clear();
                transaction.objectStore("chunks").clear();
                transaction.objectStore("routes").clear();
                meta.delete("revision");
            } else {
                const activeChunks = new Set(manifest.chunks.map((chunk) => chunk.id));
                const activeRoutes = new Set(manifest.routes.map((route) => route.id));
                for (const [storeName, active] of [
                    ["chunks", activeChunks],
                    ["routes", activeRoutes],
                ]) {
                    const request = transaction.objectStore(storeName).openCursor();
                    request.onsuccess = () => {
                        const cursor = request.result;
                        if (!cursor) return;
                        if (!active.has(cursor.key)) cursor.delete();
                        cursor.continue();
                    };
                }
            }
            meta.put({ key: "epoch", value: manifest.epoch });
            await transactionDone(transaction);
            this.preparedKey = key;
            return db;
        }

        async storedRevision(manifest) {
            const db = await this.open(manifest);
            const transaction = db.transaction("meta", "readonly");
            const current = await requestResult(
                transaction.objectStore("meta").get("revision"),
            );
            return current?.value;
        }

        async ensureSynchronized(manifest) {
            const key = `${manifest.epoch}:${manifest.revision}`;
            if (!this.syncPromises.has(key)) {
                const promise = (async () => {
                    if (await this.storedRevision(manifest) === manifest.revision) return;
                    // Routes describe the new state and cannot safely select the
                    // chunks that delete old terms. Apply every missing/revised
                    // chunk before exposing records to a query.
                    const byId = new Map(
                        manifest.chunks.map((chunk, index) => [chunk.id, index]),
                    );
                    const required = manifest.sync_chunks
                        || manifest.chunks.map((chunk) => chunk.id);
                    for (const id of required) {
                        const index = byId.get(id);
                        if (index === undefined) {
                            throw new Error(`Unknown synchronization chunk: ${id}`);
                        }
                        await this.loadChunk(index, manifest);
                    }
                    const db = await this.open(manifest);
                    const transaction = db.transaction("meta", "readwrite");
                    transaction.objectStore("meta").put({
                        key: "revision",
                        value: manifest.revision,
                    });
                    await transactionDone(transaction);
                })().catch((error) => {
                    this.syncPromises.delete(key);
                    throw error;
                });
                this.syncPromises.set(key, promise);
            }
            return this.syncPromises.get(key);
        }

        valuesFor(record, manifest) {
            const indexed = {};
            for (const field of manifest.fields) {
                const properties = field.properties
                    || (field.property ? [field.property] : []);
                if (!properties.length) continue;
                const values = properties.flatMap((property) => {
                    const value = record[property];
                    return Array.isArray(value) ? value : [value];
                });
                indexed[field.name] = [...new Set(values.flatMap(terms))];
            }
            return indexed;
        }

        async payload(file) {
            if (!this.payloadPromises.has(file)) {
                const promise = fetch(new URL(file, this.manifestUrl))
                    .then((response) => {
                        if (!response.ok) {
                            throw new Error(`Unable to load ${response.url}`);
                        }
                        return response.json();
                    })
                    .then((payload) => {
                        if (payload.version !== FORMAT_VERSION || !payload.chunks) {
                            throw new Error(`Invalid search payload: ${file}`);
                        }
                        return payload;
                    })
                    .catch((error) => {
                        this.payloadPromises.delete(file);
                        throw error;
                    });
                this.payloadPromises.set(file, promise);
            }
            return this.payloadPromises.get(file);
        }

        async dataPayload(descriptor) {
            const response = await fetch(new URL(descriptor.file, this.manifestUrl));
            if (!response.ok) {
                throw new Error(`Unable to load ${response.url}`);
            }
            const payload = await response.json();
            if (!Array.isArray(payload.operations)) {
                throw new Error(`Invalid data chunk: ${descriptor.file}`);
            }
            return payload;
        }

        async chunkIsCurrent(descriptor, manifest) {
            const db = await this.open(manifest);
            const transaction = db.transaction("chunks", "readonly");
            const current = await requestResult(
                transaction.objectStore("chunks").get(descriptor.id),
            );
            return current?.revision === descriptor.revision;
        }

        async applyChunk(descriptor, payload, manifest) {
            const db = await this.open(manifest);
            const transaction = db.transaction(
                ["records", "tombstones", "chunks"],
                "readwrite",
            );
            const records = transaction.objectStore("records");
            const tombstones = transaction.objectStore("tombstones");

            for (const [operationIndex, operation] of payload.operations.entries()) {
                const sequence = descriptor.start + operationIndex + 1;
                if (operation._deleted) {
                    const currentRequest = records.get(operation.id);
                    const tombstoneRequest = tombstones.get(operation.id);
                    let current;
                    let tombstone;
                    const apply = () => {
                        if (current === undefined || tombstone === undefined) return;
                        const known = Math.max(
                            current?._sequence || -1,
                            tombstone?._sequence || -1,
                        );
                        if (sequence >= known) {
                            records.delete(operation.id);
                            tombstones.put({ id: operation.id, _sequence: sequence });
                        }
                    };
                    currentRequest.onsuccess = () => {
                        current = currentRequest.result || null;
                        apply();
                    };
                    tombstoneRequest.onsuccess = () => {
                        tombstone = tombstoneRequest.result || null;
                        apply();
                    };
                    continue;
                }

                const currentRequest = records.get(operation.id);
                const tombstoneRequest = tombstones.get(operation.id);
                let current;
                let tombstone;
                const apply = () => {
                    if (current === undefined || tombstone === undefined) return;
                    const known = Math.max(
                        current?._sequence || -1,
                        tombstone?._sequence || -1,
                    );
                    if (sequence >= known) {
                        const record = { ...operation };
                        delete record._deleted;
                        record._sequence = sequence;
                        record._chunk = descriptor.id;
                        record._terms = this.valuesFor(record, manifest);
                        records.put(record);
                        if (tombstone) tombstones.delete(record.id);
                    }
                };
                currentRequest.onsuccess = () => {
                    current = currentRequest.result || null;
                    apply();
                };
                tombstoneRequest.onsuccess = () => {
                    tombstone = tombstoneRequest.result || null;
                    apply();
                };
            }
            transaction.objectStore("chunks").put({
                id: descriptor.id,
                revision: descriptor.revision,
                file: descriptor.file,
            });
            await transactionDone(transaction);
        }

        async loadChunk(index, manifest) {
            const descriptor = manifest.chunks[index];
            if (!descriptor || await this.chunkIsCurrent(descriptor, manifest)) {
                return false;
            }
            const key = `${descriptor.id}:${descriptor.revision}`;
            if (!this.chunkPromises.has(key)) {
                const promise = this.dataPayload(descriptor)
                    .then((payload) => this.applyChunk(descriptor, payload, manifest))
                    .finally(() => this.chunkPromises.delete(key));
                this.chunkPromises.set(key, promise);
            }
            await this.chunkPromises.get(key);
            return true;
        }

        async cachedRoute(descriptor, manifest) {
            const db = await this.open(manifest);
            const transaction = db.transaction("routes", "readonly");
            const current = await requestResult(
                transaction.objectStore("routes").get(descriptor.id),
            );
            return current?.revision === descriptor.revision ? current.data : null;
        }

        async routeData(descriptor, manifest) {
            const cached = await this.cachedRoute(descriptor, manifest);
            if (cached !== null) return cached;

            const payload = await this.payload(descriptor.file);
            this.payloadPromises.delete(descriptor.file);
            const db = await this.open(manifest);
            const transaction = db.transaction("routes", "readwrite");
            const routes = transaction.objectStore("routes");
            for (const route of manifest.routes) {
                if (route.file !== descriptor.file) continue;
                const logical = payload.chunks[route.id];
                if (!logical) {
                    throw new Error(
                        `Payload ${route.file} is missing ${route.id}`,
                    );
                }
                routes.put({
                    id: route.id,
                    revision: route.revision,
                    file: route.file,
                    data: logical.data,
                });
            }
            await transactionDone(transaction);
            return payload.chunks[descriptor.id].data;
        }

        async route(term, manifest) {
            const upper = term + "\uffff";
            const descriptors = manifest.routes.filter(
                (descriptor) => descriptor.last >= term && descriptor.first <= upper,
            );
            const decoded = await Promise.all(descriptors.map((descriptor) => {
                const key = `${descriptor.id}:${descriptor.revision}`;
                if (!this.routePromises.has(key)) {
                    this.routePromises.set(
                        key,
                        this.routeData(descriptor, manifest).then((data) => decodeRoute(
                            data,
                            manifest.route_fields,
                            manifest.chunks.length,
                        )),
                    );
                }
                return this.routePromises.get(key);
            }));
            return decoded.flat();
        }

        chunkOrder(manifest) {
            if (!manifest.chunks.some((chunk) => chunk.max_published)) {
                return manifest.chunks.map((_, index) => index);
            }
            return manifest.chunks.map((_, index) => index).sort((left, right) => {
                const byDate = String(manifest.chunks[right].max_published || "")
                    .localeCompare(String(manifest.chunks[left].max_published || ""));
                return byDate || right - left;
            });
        }

        selectedFields(fields) {
            if (fields.includes("all")) return [...INDEX_FIELDS];
            return [...new Set(fields)].filter(
                (field) => INDEX_FIELDS.includes(field),
            );
        }

        async candidateChunks(queryTerms, fields, manifest) {
            if (!queryTerms.length) return this.chunkOrder(manifest);
            const selected = this.selectedFields(fields);
            if (!selected.length) return [];

            let candidates = null;
            for (const query of queryTerms) {
                const route = await this.route(query, manifest);
                let termChunks = new Set();
                for (const [matchedTerm, postings] of route) {
                    if (!matchedTerm.startsWith(query)) continue;
                    for (const name of selected) {
                        termChunks = union(
                            termChunks,
                            new Set(postings[name] || []),
                        );
                    }
                }
                candidates = intersect(candidates, termChunks);
            }
            const order = this.chunkOrder(manifest);
            return order.filter((index) => candidates?.has(index));
        }

        async recordsForPrefix(
            query,
            fields = INDEX_FIELDS,
            after = "",
            before = "",
            resultLimit = RESULT_LIMIT,
        ) {
            const manifest = await this.manifest();
            const queryTerms = [...new Set(terms(query))];
            const selected = this.selectedFields(fields);
            const db = await this.open(manifest);
            let matches = null;

            if (queryTerms.length) {
                if (!selected.length) return [];
                for (const queryTerm of queryTerms) {
                    const termMatches = new Map();
                    for (const name of selected) {
                        let scanned = 0;
                        const transaction = db.transaction("records", "readonly");
                        const index = transaction.objectStore("records").index(name);
                        const range = IDBKeyRange.bound(
                            queryTerm,
                            queryTerm + "\uffff",
                        );
                        await new Promise((resolve, reject) => {
                            const request = index.openCursor(range);
                            request.onsuccess = () => {
                                const cursor = request.result;
                                if (!cursor || scanned >= Math.max(TERM_SCAN_LIMIT, resultLimit)) {
                                    resolve();
                                    return;
                                }
                                termMatches.set(cursor.value.id, cursor.value);
                                scanned += 1;
                                cursor.continue();
                            };
                            request.onerror = () => reject(request.error);
                        });
                    }
                    matches = matches === null
                        ? termMatches
                        : new Map(
                            [...matches].filter(([id]) => termMatches.has(id)),
                        );
                }
            } else {
                matches = new Map();
                const transaction = db.transaction("records", "readonly");
                const records = transaction.objectStore("records");
                const lower = after || undefined;
                const upper = before ? before + "T23:59:59\uffff" : undefined;
                const range = lower && upper
                    ? IDBKeyRange.bound(lower, upper)
                    : lower
                    ? IDBKeyRange.lowerBound(lower)
                    : upper
                    ? IDBKeyRange.upperBound(upper)
                    : null;
                await new Promise((resolve, reject) => {
                    const request = lower || upper
                        ? records.index("published").openCursor(range, "prev")
                        : records.openCursor();
                    request.onsuccess = () => {
                        const cursor = request.result;
                        if (!cursor || matches.size >= resultLimit) {
                            resolve();
                            return;
                        }
                        matches.set(cursor.value.id, cursor.value);
                        cursor.continue();
                    };
                    request.onerror = () => reject(request.error);
                });
            }

            return [...(matches || new Map()).values()]
                .filter((record) => !after || record.published >= after)
                .filter((record) => !before || record.published <= before + "T23:59:59")
                .sort((left, right) => (
                    String(right.published).localeCompare(String(left.published))
                ))
                .slice(0, resultLimit);
        }

        async synchronize(options = {}) {
            const manifest = await this.manifest();
            const queryTerms = [...new Set(terms(options.query || ""))];
            if (queryTerms.some(
                (term) => term.length < manifest.min_query_length
            )) return;

            const fields = options.fields || INDEX_FIELDS;
            const candidates = await this.candidateChunks(
                queryTerms,
                fields,
                manifest,
            );
            for (const index of candidates) {
                const changed = await this.loadChunk(index, manifest);
                if (changed && options.onProgress) await options.onProgress();
                if (options.stopWhen && await options.stopWhen()) return;
                if (options.signal?.aborted) return;
            }
        }
    }

    class StaticRecordCollection {
        constructor(manifestUrl) {
            this.manifestUrl = new URL(manifestUrl, document.baseURI);
            this.manifestPromise = null;
            this.bucketPromises = new Map();
            this.encoder = new TextEncoder();
        }

        refresh() {
            this.manifestPromise = null;
            this.bucketPromises.clear();
            return this.manifest();
        }

        manifest() {
            if (!this.manifestPromise) {
                this.manifestPromise = fetch(this.manifestUrl, {cache: "no-cache"})
                    .then((response) => {
                        if (!response.ok) throw new Error(`Unable to load ${response.url}`);
                        return response.json();
                    })
                    .then((manifest) => {
                        if (manifest.version !== FORMAT_VERSION
                            || manifest.kind !== "keyed-records") {
                            throw new Error("Unsupported keyed record format");
                        }
                        manifest.bucketMap = new Map(
                            manifest.buckets.map((bucket) => [bucket.index, bucket]),
                        );
                        navigator.serviceWorker?.controller?.postMessage({
                            type: "prune-directory-data",
                            base: new URL(".", this.manifestUrl).href,
                            keep: [
                                "index.json",
                                ...manifest.buckets.map((bucket) => bucket.file),
                            ],
                        });
                        return manifest;
                    });
            }
            return this.manifestPromise;
        }

        bucketIndex(value, count) {
            let hash = 0x811c9dc5;
            for (const byte of this.encoder.encode(value)) {
                hash = Math.imul(hash ^ byte, 0x01000193) >>> 0;
            }
            return hash % count;
        }

        async record(id) {
            const manifest = await this.manifest();
            const descriptor = manifest.bucketMap.get(
                this.bucketIndex(id, manifest.bucket_count),
            );
            if (!descriptor) return null;
            if (!this.bucketPromises.has(descriptor.file)) {
                this.bucketPromises.set(descriptor.file, fetch(
                    new URL(descriptor.file, this.manifestUrl),
                ).then((response) => {
                    if (!response.ok) throw new Error(`Unable to load ${response.url}`);
                    return response.json();
                }));
            }
            const payload = await this.bucketPromises.get(descriptor.file);
            const encoded = payload.records?.[id];
            if (!encoded) return null;
            return {id, ...encoded};
        }
    }

    function closeDatabases() {
        OPEN_DATABASES.forEach((database) => database.close());
        OPEN_DATABASES.clear();
    }

    window.CppSearchCache = {
        StaticSearchCollection,
        StaticRecordCollection,
        closeDatabases,
        terms,
    };
})();
