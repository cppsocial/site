import re

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor


class GitHubAdmonitionsPreprocessor(Preprocessor):
    pattern = re.compile(
        r"^> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$"
    )
    title_pattern = re.compile(r"^\*\*(.+)\*\*$")

    def run(self, lines):
        output = []
        i = 0

        while i < len(lines):
            match = self.pattern.match(lines[i])

            if not match:
                output.append(lines[i])
                i += 1
                continue

            kind = match.group(1).lower()
            body = []
            i += 1

            while i < len(lines) and lines[i].startswith(">"):
                line = lines[i][1:].removeprefix(" ")
                body.append(line)
                i += 1

            title = None
            if body:
                title_match = self.title_pattern.match(body[0])
                if title_match:
                    title = title_match.group(1)
                    body = body[1:]

                    if body and not body[0]:
                        body = body[1:]

            header = f"!!! {kind}"
            if title:
                title = title.replace('"', '\\"')
                header += f' "{title}"'

            output.append(header)
            output.extend(f"    {line}" for line in body)

        return output


class GitHubAdmonitionsExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(
            GitHubAdmonitionsPreprocessor(md),
            "github_admonitions",
            25,
        )


def makeExtension(**kwargs):
    return GitHubAdmonitionsExtension(**kwargs)


_MARKDOWN_HEADING = re.compile(
    r"^[ \t]{0,3}(?P<marks>#{1,6})[ \t]+"
    r"(?P<title>.*?)(?:[ \t]+#+)?[ \t]*$"
)


def select_sections(content: str, titles: list[str]) -> str:
    """Select complete ATX-heading sections, retaining source-file order."""
    wanted = set(titles)
    headings: list[tuple[int, int, str]] = []
    lines = content.splitlines(keepends=True)
    fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        fence_match = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match[1]
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            continue
        if fence is not None:
            continue
        match = _MARKDOWN_HEADING.match(stripped)
        if match:
            headings.append((index, len(match["marks"]), match["title"]))

    found = {title for _, _, title in headings if title in wanted}
    missing = [title for title in titles if title not in found]
    if missing:
        names = ", ".join(repr(title) for title in missing)
        raise ValueError(f"Markdown headings not found: {names}")

    ranges: list[tuple[int, int]] = []
    for position, (start, level, title) in enumerate(headings):
        if title not in wanted:
            continue
        end = len(lines)
        for next_start, next_level, _ in headings[position + 1:]:
            if next_level <= level:
                end = next_start
                break
        ranges.append((start, end))

    # Parent and child selections can overlap. Merge them so source text is never
    # duplicated, and always preserve its original ordering.
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return "\n".join("".join(lines[start:end]).rstrip() for start, end in merged)
