import { createText } from "../shared/dom";

type FeedRecord = {
  channel: string;
  description?: string;
  id: string;
  published: string;
  source: string;
  thumbnail_url?: string;
  title: string;
  url: string;
};

type FeedCardsOptions = {
  blogAvatars: Map<string, string>;
  continueReadingLabel: string;
  copy: Record<string, string>;
  cardCopy: Record<string, string>;
};

export function createFeedCards({
  blogAvatars,
  continueReadingLabel,
  copy,
  cardCopy,
}: FeedCardsOptions) {
  function shortDate(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return String(value).slice(0, 10);
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
  }

  function blogPost(record: FeedRecord) {
    const card = document.createElement("article");
    card.className = "blog-post-card";
    card.tabIndex = 0;
    card.setAttribute("role", "link");
    card.dataset.cardHref = record.url;
    const source = document.createElement("div");
    source.className = "blog-post-card__source";
    const avatarUrl = blogAvatars.get(record.source);
    const avatar = document.createElement(avatarUrl ? "img" : "span");
    avatar.className = "blog-post-card__avatar";
    if (avatar instanceof HTMLImageElement) {
      avatar.src = avatarUrl ?? "";
      avatar.alt = "";
      avatar.loading = "lazy";
      avatar.decoding = "async";
      avatar.referrerPolicy = "no-referrer";
    } else {
      avatar.classList.add("blog-post-card__avatar--monogram");
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = record.source.slice(0, 1);
    }
    source.append(avatar);
    const sourceLabel = document.createElement("p");
    createText(sourceLabel, "strong", record.source);
    const time = createText(sourceLabel, "time", shortDate(record.published));
    time.dateTime = record.published;
    source.append(sourceLabel);
    card.append(source);
    const heading = document.createElement("h3");
    const link = createText(heading, "a", record.title);
    link.href = record.url;
    link.target = "_blank";
    link.rel = "noopener";
    card.append(heading);
    const description = document.createElement("div");
    description.className = "blog-post-card__description";
    if (record.description) description.innerHTML = record.description;
    if (description.textContent) card.append(description);
    const more = createText(
      card,
      "a",
      `${continueReadingLabel || copy.continue_reading} ↗`,
    );
    more.className = "blog-post-card__more";
    more.href = record.url;
    more.target = "_blank";
    more.rel = "noopener";
    return card;
  }

  function youtubeVideo(record: FeedRecord) {
    const card = document.createElement("article");
    card.className = "card video-card";
    card.tabIndex = 0;
    card.setAttribute("role", "link");
    card.dataset.cardHref = record.url;
    const visual = document.createElement("a");
    visual.className = "video-card__visual";
    visual.href = record.url;
    visual.target = "_blank";
    visual.rel = "noopener";
    visual.setAttribute(
      "aria-label",
      `${cardCopy.watch_prefix} ${record.title} ${cardCopy.youtube_suffix}`,
    );
    if (record.thumbnail_url) {
      const image = document.createElement("img");
      image.src = record.thumbnail_url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.referrerPolicy = "no-referrer";
      visual.append(image);
    }
    const play = createText(visual, "span", "▶");
    play.className = "video-card__play";
    play.setAttribute("aria-hidden", "true");
    card.append(visual);
    const body = document.createElement("div");
    body.className = "video-card__body";
    const heading = document.createElement("h3");
    const link = createText(heading, "a", record.title);
    link.href = record.url;
    link.target = "_blank";
    link.rel = "noopener";
    body.append(heading);
    const byline = createText(body, "p", `${record.channel} · `);
    byline.className = "video-card__byline";
    const time = createText(byline, "time", record.published.slice(0, 10));
    time.dateTime = record.published;
    card.append(body);
    return card;
  }

  return { blogPost, youtubeVideo };
}
