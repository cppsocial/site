export function createText<Name extends keyof HTMLElementTagNameMap>(
  parent: ParentNode,
  name: Name,
  value: string,
): HTMLElementTagNameMap[Name] {
  const element = document.createElement(name);
  element.textContent = value;
  parent.append(element);
  return element;
}

export function eventElement(event: Event): Element | null {
  return event.target instanceof Element ? event.target : null;
}

export function queryRequired<ElementType extends Element>(
  root: ParentNode,
  selector: string,
): ElementType {
  const element = root.querySelector<ElementType>(selector);
  if (!element) throw new Error(`Missing required element: ${selector}`);
  return element;
}

export function parseJsonScript<Value>(
  root: ParentNode,
  selector: string,
): Value {
  const script = queryRequired<HTMLScriptElement>(root, selector);
  return JSON.parse(script.textContent ?? "null") as Value;
}
