import { eventElement } from "./dom";

export type DialogContext = {
  card: HTMLElement;
  content: HTMLElement;
  dialog: HTMLDialogElement;
  opener: HTMLElement;
};

export type TemplateDialogOptions = {
  cardSelector: string;
  closeSelector: string;
  content: HTMLElement;
  dialog: HTMLDialogElement;
  documentClass: string;
  openSelector: string;
  templateSelector: string;
  afterOpen?: (context: DialogContext) => void | Promise<void>;
  beforeClose?: (context: DialogContext) => void | Promise<void>;
};

export class TemplateDialogController {
  private context: DialogContext | null = null;
  private closing = false;

  constructor(private readonly options: TemplateDialogOptions) {
    document.addEventListener("click", this.openFromEvent);
    options.dialog.addEventListener("click", this.closeFromEvent);
    options.dialog.addEventListener("cancel", this.cancel);
    options.dialog.addEventListener("close", this.closed);
  }

  private readonly openFromEvent = (event: MouseEvent): void => {
    const opener = eventElement(event)?.closest<HTMLElement>(
      this.options.openSelector,
    );
    if (!opener) return;
    const card = opener.closest<HTMLElement>(this.options.cardSelector);
    const template = card?.querySelector<HTMLTemplateElement>(
      this.options.templateSelector,
    );
    if (!card || !template) return;
    this.options.content.replaceChildren(template.content.cloneNode(true));
    this.context = {
      card,
      content: this.options.content,
      dialog: this.options.dialog,
      opener,
    };
    this.options.dialog.showModal();
    document.documentElement.classList.add(this.options.documentClass);
    this.options.content
      .querySelector<HTMLElement>(this.options.closeSelector)
      ?.focus();
    void this.options.afterOpen?.(this.context);
  };

  private readonly closeFromEvent = (event: MouseEvent): void => {
    const target = eventElement(event);
    if (
      target === this.options.dialog ||
      target?.closest(this.options.closeSelector)
    ) {
      void this.close();
    }
  };

  private readonly cancel = (event: Event): void => {
    event.preventDefault();
    void this.close();
  };

  async close(): Promise<void> {
    if (!this.options.dialog.open || !this.context || this.closing) return;
    this.closing = true;
    await this.options.beforeClose?.(this.context);
    this.options.dialog.close();
  }

  destroy(): void {
    document.removeEventListener("click", this.openFromEvent);
    this.options.dialog.removeEventListener("click", this.closeFromEvent);
    this.options.dialog.removeEventListener("cancel", this.cancel);
    this.options.dialog.removeEventListener("close", this.closed);
  }

  private readonly closed = (): void => {
    document.documentElement.classList.remove(this.options.documentClass);
    this.options.content.replaceChildren();
    this.context?.opener.focus();
    this.context = null;
    this.closing = false;
  };
}
