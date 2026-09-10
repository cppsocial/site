import { initStoredChoice } from "../shared/choice";

(() => {
  "use strict";

  const root = document.querySelector<HTMLElement>("[data-package-graph]");
  const canvas = root?.querySelector<HTMLCanvasElement>(
    "[data-package-graph-canvas]",
  );
  const list = document.querySelector<HTMLElement>("[data-package-list-view]");
  const controls = Array.from(
    document.querySelectorAll<HTMLButtonElement>("[data-package-view]"),
  );
  if (!root || !canvas || !list || !controls.length) return;

  const context = canvas.getContext("2d");
  const status = root.querySelector<HTMLElement>("[data-package-graph-status]");
  const legend = root.querySelector<HTMLElement>("[data-package-graph-legend]");
  const tooltip = root.querySelector<HTMLElement>(
    "[data-package-graph-tooltip]",
  );
  const fullscreen = root.querySelector<HTMLButtonElement>(
    "[data-package-graph-fullscreen]",
  );
  const managerOrder = [
    "conan",
    "vcpkg",
    "spack",
    "xmake",
    "bazel",
    "meson",
    "cppget",
    "hunter",
  ];
  const managerLabels = new Map(
    Array.from(
      document.querySelectorAll<HTMLButtonElement>(
        "[data-search-manager-choice]",
      ),
    ).map((choice) => [choice.value, choice.textContent.trim()]),
  );
  const managerColors = new Map([
    ["conan", "#ef8c5b"],
    ["vcpkg", "#58a6ff"],
    ["spack", "#79c99e"],
    ["xmake", "#ca85ff"],
    ["bazel", "#f2c14e"],
    ["meson", "#ef5da8"],
    ["cppget", "#70d6ff"],
    ["hunter", "#a8dadc"],
  ]);
  const view = { width: 0, height: 0, scale: 1, x: 0, y: 0 };
  let nodes = [];
  let edges = [];
  let nodeById = new Map();
  let matchedIds = null;
  let selectedIds = null;
  let activeManagers = new Set();
  const hiddenManagers = new Set();
  let loaded = false;
  let loading = null;
  let hovered = null;
  let selected = null;
  let pointer = null;
  let animationFrame = 0;

  const css = (name, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() ||
    fallback;

  function hash(value) {
    let result = 2166136261;
    for (const character of value) {
      result ^= character.charCodeAt(0);
      result = Math.imul(result, 16777619);
    }
    return (result >>> 0) / 4294967295;
  }

  function layoutGraph(records) {
    nodeById = new Map(
      records.map((record) => [
        record.id,
        { ...record, inbound: 0, x: 0, y: 0, radius: 2 },
      ]),
    );
    edges = [];
    for (const record of records) {
      const source = nodeById.get(record.id);
      for (const dependencyId of new Set(record.dependencies || [])) {
        const target = nodeById.get(dependencyId);
        if (!target || target === source) continue;
        target.inbound += 1;
        edges.push([source, target]);
      }
    }
    nodes = [...nodeById.values()].sort(
      (left, right) =>
        right.inbound - left.inbound || left.id.localeCompare(right.id),
    );
    const maximum = Math.max(1, nodes[0]?.inbound || 0);
    const count = Math.max(1, nodes.length - 1);
    nodes.forEach((node, index) => {
      node.radius = Math.min(11, 1.45 + Math.log2(node.inbound + 1) * 1.25);
      if (index === 0) return;
      const primary = node.managers[0] || managerOrder[0];
      const managerIndex = Math.max(0, managerOrder.indexOf(primary));
      const centerAngle = (managerIndex / managerOrder.length) * Math.PI * 2;
      const jitter =
        (hash(node.id) - 0.5) * ((Math.PI * 2) / managerOrder.length) * 0.9;
      const rankRadius = 85 + Math.sqrt(index / count) * 640;
      const centralityPull = 1 - Math.sqrt(node.inbound / maximum) * 0.38;
      const sharedPull = node.managers.length > 1 ? 0.76 : 1;
      const radius = rankRadius * centralityPull * sharedPull;
      node.x = Math.cos(centerAngle + jitter) * radius;
      node.y = Math.sin(centerAngle + jitter) * radius * 0.7;
    });
  }

  function createLegend() {
    legend.replaceChildren();
    managerOrder.forEach((manager) => {
      const item = document.createElement("button");
      item.type = "button";
      item.setAttribute("aria-pressed", "true");
      const label = managerLabels.get(manager) || manager;
      item.title = `Hide ${label}`;
      const swatch = document.createElement("i");
      swatch.style.background = managerColors.get(manager);
      item.append(swatch, label);
      item.addEventListener("click", () => {
        if (hiddenManagers.has(manager)) {
          hiddenManagers.delete(manager);
        } else {
          hiddenManagers.add(manager);
        }
        const visible = !hiddenManagers.has(manager);
        item.setAttribute("aria-pressed", String(visible));
        item.title = `${visible ? "Hide" : "Show"} ${label}`;
        if (selected && !isVisible(selected)) {
          selectNode(null);
          hovered = null;
          tooltip.hidden = true;
        }
        draw();
      });
      legend.append(item);
    });
  }

  async function load() {
    if (loaded) return;
    if (loading) return loading;
    loading = fetch(root.dataset.graphSource)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load ${response.url}`);
        return response.json();
      })
      .then((data) => {
        layoutGraph(data.nodes || []);
        createLegend();
        loaded = true;
        status.textContent = nodes.length
          ? `${nodes.length.toLocaleString()} packages · ${edges.length.toLocaleString()} tracked dependencies`
          : "No package relationships are available.";
        fit();
      })
      .catch((error) => {
        console.error(error);
        status.textContent = "The dependency graph could not be loaded.";
      });
    return loading;
  }

  function resize() {
    if (root.hidden) return;
    const bounds = root.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const previousWidth = view.width;
    const previousHeight = view.height;
    view.width = Math.max(1, bounds.width);
    view.height = Math.max(1, bounds.height);
    if (previousWidth && previousHeight) {
      view.x += (view.width - previousWidth) / 2;
      view.y += (view.height - previousHeight) / 2;
    }
    canvas.width = Math.round(view.width * ratio);
    canvas.height = Math.round(view.height * ratio);
    canvas.style.width = `${view.width}px`;
    canvas.style.height = `${view.height}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
  }

  function fit() {
    resize();
    view.scale = Math.min(view.width / 1550, view.height / 1080);
    view.x = view.width / 2;
    view.y = view.height / 2 + 20;
    draw();
  }

  function screen(node) {
    return {
      x: view.x + node.x * view.scale,
      y: view.y + node.y * view.scale,
    };
  }

  function isMatch(node) {
    const managerMatch =
      !activeManagers.size ||
      [...activeManagers].every((manager) => node.managers.includes(manager));
    return (
      isVisible(node) &&
      managerMatch &&
      (!matchedIds || matchedIds.has(node.id)) &&
      (!selectedIds || selectedIds.has(node.id))
    );
  }

  function isVisible(node) {
    return node.managers.some((manager) => !hiddenManagers.has(manager));
  }

  function isFiltering() {
    return Boolean(
      matchedIds || activeManagers.size || selectedIds || hiddenManagers.size,
    );
  }

  function selectNode(node) {
    selected = node;
    selectedIds = node ? new Set([node.id]) : null;
    if (!node) return;
    for (const [source, target] of edges) {
      if (source === node || target === node) {
        selectedIds.add(source.id);
        selectedIds.add(target.id);
      }
    }
  }

  function draw() {
    cancelAnimationFrame(animationFrame);
    animationFrame = requestAnimationFrame(() => {
      context.clearRect(0, 0, view.width, view.height);
      const primary = css("--primary", "#f4f7fb");
      const muted = css("--secondary", "#8b95a5");
      const lightTheme = document.documentElement.dataset.theme === "light";
      const filtering = isFiltering();
      let visibleEdgeCount = 0;
      let visibleNodeCount = 0;

      context.lineWidth = 0.55;
      for (const [source, target] of edges) {
        if (!isVisible(source) || !isVisible(target)) continue;
        if (isMatch(source) && isMatch(target)) visibleEdgeCount += 1;
        const interactiveHover = hovered && isMatch(hovered);
        const highlighted =
          (interactiveHover && (source === hovered || target === hovered)) ||
          source === selected ||
          target === selected;
        if (filtering && (!isMatch(source) || !isMatch(target))) continue;
        const start = screen(source);
        const end = screen(target);
        context.strokeStyle = highlighted
          ? lightTheme
            ? "rgba(18, 105, 155, .78)"
            : "rgba(123, 211, 255, .72)"
          : lightTheme
            ? filtering
              ? "rgba(45, 68, 94, .28)"
              : "rgba(45, 68, 94, .2)"
            : filtering
              ? "rgba(130, 150, 175, .14)"
              : "rgba(130, 150, 175, .075)";
        context.beginPath();
        context.moveTo(start.x, start.y);
        context.lineTo(end.x, end.y);
        context.stroke();
      }

      for (const node of nodes) {
        if (!isVisible(node)) continue;
        const point = screen(node);
        const match = isMatch(node);
        if (match) visibleNodeCount += 1;
        const emphasized = node === hovered || node === selected;
        const radius =
          Math.max(1.1, node.radius * Math.sqrt(view.scale)) *
          (emphasized ? 1.7 : match && filtering ? 1.25 : 1);
        context.globalAlpha =
          filtering && !match ? 0.075 : emphasized ? 1 : 0.82;
        const supported = node.managers.filter(
          (manager) => !hiddenManagers.has(manager),
        );
        for (const [index, manager] of supported.entries()) {
          const start = -Math.PI / 2 + (index / supported.length) * Math.PI * 2;
          const end =
            -Math.PI / 2 + ((index + 1) / supported.length) * Math.PI * 2;
          context.fillStyle = managerColors.get(manager) || muted;
          context.beginPath();
          context.moveTo(point.x, point.y);
          context.arc(point.x, point.y, radius, start, end);
          context.closePath();
          context.fill();
        }
      }
      context.globalAlpha = 1;

      const labels = new Set(filtering ? [] : nodes.slice(0, 12));
      if (filtering) {
        nodes
          .filter(isMatch)
          .slice(0, 24)
          .forEach((node) => labels.add(node));
      }
      if (hovered && isMatch(hovered)) labels.add(hovered);
      if (selected) labels.add(selected);
      context.font = "600 11px system-ui, sans-serif";
      context.textBaseline = "middle";
      for (const node of labels) {
        if (!isVisible(node)) continue;
        const point = screen(node);
        context.globalAlpha = filtering && !isMatch(node) ? 0.2 : 0.92;
        context.fillStyle = primary;
        context.fillText(node.label, point.x + node.radius + 5, point.y);
      }
      context.globalAlpha = 1;
      if (loaded) {
        status.textContent = `${visibleNodeCount.toLocaleString()} packages · ${visibleEdgeCount.toLocaleString()} tracked dependencies`;
      }
    });
  }

  function findNode(clientX, clientY) {
    const bounds = canvas.getBoundingClientRect();
    const x = clientX - bounds.left;
    const y = clientY - bounds.top;
    const nearest = (candidates, hitRadius) => {
      let result = null;
      let distance = hitRadius;
      for (const node of candidates) {
        const point = screen(node);
        const candidate = Math.hypot(point.x - x, point.y - y);
        if (candidate < distance) {
          distance = candidate;
          result = node;
        }
      }
      return result;
    };
    return (
      nearest(nodes.filter(isMatch), 24) || nearest(nodes.filter(isVisible), 10)
    );
  }

  function showTooltip(node, event) {
    if (!node || !isMatch(node)) {
      tooltip.hidden = true;
      return;
    }
    tooltip.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = node.label;
    const metadata = document.createElement("span");
    metadata.textContent = `${node.inbound.toLocaleString()} dependents · ${node.managers.map((manager) => managerLabels.get(manager) || manager).join(" + ")}`;
    tooltip.append(title, metadata);
    tooltip.hidden = false;
    const bounds = root.getBoundingClientRect();
    tooltip.style.left = `${Math.min(event.clientX - bounds.left + 14, bounds.width - 240)}px`;
    tooltip.style.top = `${Math.max(12, event.clientY - bounds.top + 14)}px`;
  }

  const setView = initStoredChoice<"list" | "graph">({
    apply: (name) => {
      const graph = name === "graph";
      root.hidden = !graph;
      list.hidden = graph;
      if (graph) load().then(() => requestAnimationFrame(resize));
    },
    buttons: controls,
    initial: "list",
    storageKey: "package-catalog-view",
    value: (control) =>
      control.dataset.packageView === "graph" ? "graph" : "list",
  });

  if (!root.requestFullscreen) {
    fullscreen.hidden = true;
  } else {
    fullscreen.addEventListener("click", async () => {
      try {
        if (document.fullscreenElement === root) {
          await document.exitFullscreen();
        } else {
          await root.requestFullscreen();
        }
      } catch (error) {
        console.error(error);
      }
    });
    document.addEventListener("fullscreenchange", () => {
      const active = document.fullscreenElement === root;
      const label = active
        ? fullscreen.dataset.exitLabel
        : fullscreen.dataset.enterLabel;
      fullscreen.setAttribute("aria-label", label);
      fullscreen.title = label;
      requestAnimationFrame(resize);
    });
  }

  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    pointer = {
      x: event.clientX,
      y: event.clientY,
      originX: view.x,
      originY: view.y,
      moved: false,
    };
  });
  canvas.addEventListener("pointermove", (event) => {
    if (pointer) {
      const dx = event.clientX - pointer.x;
      const dy = event.clientY - pointer.y;
      pointer.moved ||= Math.hypot(dx, dy) > 3;
      view.x = pointer.originX + dx;
      view.y = pointer.originY + dy;
      tooltip.hidden = true;
      draw();
      return;
    }
    const next = findNode(event.clientX, event.clientY);
    if (next !== hovered) {
      hovered = next;
      canvas.style.cursor = hovered && isMatch(hovered) ? "pointer" : "grab";
      draw();
    }
    showTooltip(hovered, event);
  });
  canvas.addEventListener("pointerup", (event) => {
    const wasMoved = pointer?.moved;
    pointer = null;
    if (wasMoved) return;
    const clicked = findNode(event.clientX, event.clientY);
    if (selected && clicked !== selected) {
      selectNode(null);
      hovered = clicked;
    } else if (!clicked) {
      selectNode(null);
      hovered = null;
    } else if (isMatch(clicked)) {
      selectNode(clicked);
    }
    draw();
    showTooltip(clicked, event);
  });
  canvas.addEventListener("dblclick", (event) => {
    const clicked = findNode(event.clientX, event.clientY);
    if (!clicked || !isMatch(clicked)) return;
    selectNode(clicked);
    window.dispatchEvent(
      new CustomEvent("cpp:package-select", {
        detail: { id: clicked.id, label: clicked.label },
      }),
    );
    setView("list");
  });
  canvas.addEventListener("pointerleave", () => {
    if (pointer) return;
    hovered = null;
    tooltip.hidden = true;
    draw();
  });
  canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const bounds = canvas.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      const previous = view.scale;
      view.scale = Math.max(
        0.18,
        Math.min(10, view.scale * Math.exp(-event.deltaY * 0.001)),
      );
      view.x = x - ((x - view.x) * view.scale) / previous;
      view.y = y - ((y - view.y) * view.scale) / previous;
      draw();
    },
    { passive: false },
  );

  window.addEventListener("resize", resize);
  window.addEventListener("cpp:package-search", (baseEvent) => {
    const event = baseEvent as CustomEvent<{
      filtering: boolean;
      managers?: string[];
      matches: string[];
    }>;
    matchedIds = event.detail.filtering ? new Set(event.detail.matches) : null;
    activeManagers = new Set(event.detail.managers || []);
    if (loaded) draw();
  });
  new MutationObserver(() => draw()).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
})();
