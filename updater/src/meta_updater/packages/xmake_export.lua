import("core.base.json")
import("core.base.option")
import("core.base.semver")
import("core.package.package")


local OPTIONS = {
    {nil, "repo", "kv", nil, "Path to the local xmake-repo checkout."},
    {nil, "out", "kv", nil, "Output JSON file."},
}


-- Probe the host/default evaluation as well as the main target platforms.
--
-- false means no explicit platform is passed to load_from_repository().
local PLATFORMS = {
    false,
    "windows",
    "linux",
    "macosx",
    "iphoneos",
    "android",
    "mingw",
    "msys",
    "bsd",
    "wasm",
    "cross",
    "harmony",
}


local function _array(values)
    return json.mark_as_array(values or {})
end


local function _add(set, value)
    if value == nil then
        return
    end

    value = tostring(value)

    if value ~= "" then
        set[value] = true
    end
end


local function _add_values(set, values)
    if values == nil then
        return
    end

    if type(values) ~= "table" then
        _add(set, values)
        return
    end

    if #values > 0 then
        for _, value in ipairs(values) do
            _add(set, value)
        end
    else
        -- add_deps()/add_components() can be represented as keyed tables
        -- when extra configuration is attached. In that case the keys are
        -- the names we want to export.
        for key, _ in pairs(values) do
            _add(set, key)
        end
    end
end


local function _set_to_array(set)
    local values = {}

    for value, _ in pairs(set) do
        table.insert(values, value)
    end

    table.sort(values)

    return _array(values)
end


local function _version_less(a, b)
    if semver.is_valid(a) and semver.is_valid(b) then
        return semver.compare(a, b) < 0
    end

    return a < b
end


local function _resolve_url(instance, url, version)
    if not url or not version then
        return nil
    end

    if not url:find("%$%(version%)")
        and not url:find("%$%(version_nodot%)") then
        return url
    end

    local effective = version
    local filter = instance:url_version(url)

    if filter then
        local argument = version

        try {
            function()
                argument = semver.new(version)
            end,
            catch {
                function()
                end
            }
        }

        local result = filter(argument or version)

        if result ~= nil then
            effective = tostring(result)
        end
    end

    local replacement = effective:gsub("%%", "%%%%")
    local resolved = url:gsub("%$%(version%)", replacement)

    local nodot = effective:gsub("%.", ""):gsub("%%", "%%%%")
    resolved = resolved:gsub("%$%(version_nodot%)", nodot)

    return resolved
end


local function _load_package(name, packagedir, packagefile, plat)
    local options = {
        packagefile = packagefile,
    }

    if plat then
        options.plat = plat
    end

    local instance, errors = package.load_from_repository(
        name,
        packagedir,
        options
    )

    assert(instance, errors or ("failed to load package " .. name))

    if plat then
        instance:plat_set(plat)
    end

    -- Initialize on_source() without running on_load()/install logic.
    instance:_init_source()

    return instance
end


local function _add_checksum(checksums, sourcehash)
    if type(sourcehash) ~= "string" then
        return
    end

    -- Xmake uses values <= 40 characters for Git revisions. Archive
    -- packages in xmake-repo use 64-character SHA-256 digests.
    if #sourcehash == 64 and sourcehash:match("^%x+$") then
        _add(
            checksums,
            "sha256:" .. sourcehash:lower()
        )
    end
end


local function _collect_metadata(result, instance)
    if not result.description then
        result.description = instance:get("description")
    end

    if not result.homepage then
        result.homepage = instance:get("homepage")
    end

    _add_values(
        result.urls,
        instance:urls()
    )

    _add_values(
        result.licenses,
        instance:get("license")
    )

    _add_values(
        result.dependencies,
        instance:get("deps")
    )

    _add_values(
        result.components,
        instance:get("components")
    )

    _add_values(
        result.extsources,
        instance:extsources()
    )

    if not result.kind then
        result.kind = instance:kind()
    end

    for _, name in ipairs(instance:get("configs") or {}) do
        if not result.configs[name] then
            local extra = instance:extraconf("configs", name) or {}
            local values = {}
            for _, value in ipairs(extra.values or {}) do
                table.insert(values, tostring(value))
            end
            result.configs[name] = {
                description = extra.description,
                default = extra.default ~= nil and tostring(extra.default) or nil,
                type = extra.type,
                values = _array(values),
            }
        end
    end
end


local function _collect_versions(result, instance)
    local urls = instance:urls()

    for _, raw_version in ipairs(instance:versions()) do
        local version = tostring(raw_version)

        local item = result.versions[version]

        if not item then
            item = {
                source_urls = {},
                checksums = {},
            }

            result.versions[version] = item
        end

        instance:version_set(version, "version")

        -- The normal non-aliased version checksum.
        _add_checksum(
            item.checksums,
            instance:sourcehash()
        )

        for _, raw_url in ipairs(urls) do
            local resolved_url = nil

            try {
                function()
                    resolved_url = _resolve_url(
                        instance,
                        raw_url,
                        version
                    )
                end,
                catch {
                    function()
                    end
                }
            }

            if resolved_url then
                _add(
                    item.source_urls,
                    resolved_url
                )
            end

            -- Xmake permits URL aliases to have their own source hash
            -- for the same logical package version.
            local alias = instance:url_alias(raw_url)

            if alias then
                _add_checksum(
                    item.checksums,
                    instance:sourcehash(alias)
                )
            end
        end
    end
end


local function _collect_instance(result, instance, plat)
    _collect_metadata(result, instance)
    _collect_versions(result, instance)
    _add(result.platforms, plat or "default")
end


local function _finish_package(result)
    local versions = {}

    for version, item in pairs(result.versions) do
        table.insert(
            versions,
            {
                version = version,
                source_urls = _set_to_array(
                    item.source_urls
                ),
                checksums = _set_to_array(
                    item.checksums
                ),
            }
        )
    end

    table.sort(
        versions,
        function(a, b)
            return _version_less(
                a.version,
                b.version
            )
        end
    )

    return {
        name = result.name,
        recipe = result.recipe,
        description = result.description,
        homepage = result.homepage,
        urls = _set_to_array(result.urls),
        licenses = _set_to_array(result.licenses),
        dependencies = _set_to_array(
            result.dependencies
        ),
        components = _set_to_array(
            result.components
        ),
        extsources = _set_to_array(
            result.extsources
        ),
        platforms = _set_to_array(
            result.platforms
        ),
        kind = result.kind,
        configs = result.configs,
        versions = _array(versions),
    }
end


function main(...)
    local args = option.parse(
        {...},
        OPTIONS,
        "Export xmake-repo package metadata."
    )

    assert(
        args.repo,
        "--repo is required"
    )

    assert(
        args.out,
        "--out is required"
    )

    local repo = path.absolute(args.repo)
    local out = path.absolute(args.out)

    assert(
        os.isdir(repo),
        "repository directory not found: " .. repo
    )

    local packages = {}
    local skipped = {}

    local oldir = os.cd(repo)

    for _, packagedir in ipairs(
        os.dirs(
            path.join(
                "packages",
                "*",
                "*"
            )
        )
    ) do
        local name = path.filename(packagedir)

        local letter = path.filename(
            path.directory(packagedir)
        )

        local packagefile = path.join(
            packagedir,
            "xmake.lua"
        )

        local result = {
            name = name,
            recipe = string.format(
                "packages/%s/%s/xmake.lua",
                letter,
                name
            ),
            description = nil,
            homepage = nil,
            urls = {},
            licenses = {},
            dependencies = {},
            components = {},
            extsources = {},
            platforms = {},
            configs = {},
            kind = nil,
            versions = {},
        }

        local loaded = false
        local template = false
        local errors = {}

        for _, platform_value in ipairs(PLATFORMS) do
            local plat = platform_value or nil

            try {
                function()
                    local instance = _load_package(
                        name,
                        packagedir,
                        packagefile,
                        plat
                    )

                    if instance:is_template() then
                        template = true
                        return
                    end

                    loaded = true

                    _collect_instance(
                        result,
                        instance,
                        plat
                    )
                end,
                catch {
                    function(error)
                        local platform_name =
                            plat or "default"

                        table.insert(
                            errors,
                            platform_name
                                .. ": "
                                .. tostring(error)
                        )
                    end
                }
            }
        end

        if not template then
            if loaded then
                table.insert(
                    packages,
                    _finish_package(result)
                )
            else
                table.insert(
                    skipped,
                    {
                        name = name,
                        error = table.concat(
                            errors,
                            "\n"
                        ),
                    }
                )
            end
        end
    end

    os.cd(oldir)

    table.sort(
        packages,
        function(a, b)
            return a.name < b.name
        end
    )

    table.sort(
        skipped,
        function(a, b)
            return a.name < b.name
        end
    )

    os.mkdir(
        path.directory(out)
    )

    json.savefile(
        out,
        {
            packages = _array(packages),
            skipped = _array(skipped),
        }
    )
end
