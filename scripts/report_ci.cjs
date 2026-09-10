const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");

const MARKER = "<!-- cppsocial:ci-report -->";
const WORKFLOW_NAMES = new Set([
  "Build",
  "Check - Assets",
  "Check - Content and Data",
  "Check - Discord",
  "Check - Frontend",
  "Check - Makefile",
  "Check - Python",
  "Check - Templates",
  "Check - YAML",
  "Test - Scripts",
  "Test - Updater",
]);
const FORMAT_COMMANDS = new Map([
  ["Check - Assets", "npm run format:assets"],
  ["Check - Frontend", "npm run format:frontend"],
  ["Check - Makefile", "make format-makefile"],
  ["Check - Python", "make format-python"],
  ["Check - Templates", "make format-templates"],
  ["Check - YAML", "make format-yaml"],
]);

function artifactUrl(owner, repo, run, artifact) {
  return (
    `https://github.com/${owner}/${repo}/actions/runs/${run.id}` +
    `/artifacts/${artifact.id}`
  );
}

function readArtifactFile({ artifact, core, filename, maxChars, owner, repo }) {
  if (!artifact || artifact.size_in_bytes > 1024 * 1024) {
    return null;
  }
  const archivePath = path.join(
    process.env.RUNNER_TEMP,
    `ci-report-${artifact.id}.zip`,
  );
  try {
    const archive = childProcess.execFileSync(
      "gh",
      ["api", `repos/${owner}/${repo}/actions/artifacts/${artifact.id}/zip`],
      { env: process.env, maxBuffer: 1024 * 1024 },
    );
    fs.writeFileSync(archivePath, archive, { mode: 0o600 });
    const entries = childProcess
      .execFileSync("unzip", ["-Z1", archivePath], {
        encoding: "utf8",
        maxBuffer: 4096,
      })
      .trim()
      .split("\n");
    if (entries.length !== 1 || entries[0] !== filename) {
      core.warning(`Unexpected contents in artifact ${artifact.id}`);
      return null;
    }
    const output = childProcess.execFileSync(
      "unzip",
      ["-p", archivePath, filename],
      { encoding: "utf8", maxBuffer: 1024 * 1024 },
    );
    const cleaned = [...output]
      .filter(
        (character) =>
          character === "\t" ||
          character === "\n" ||
          character === "\r" ||
          character.codePointAt(0) >= 0x20,
      )
      .join("");
    return cleaned.length > maxChars
      ? `${cleaned.slice(0, maxChars)}\n... output truncated ...`
      : cleaned;
  } catch (error) {
    core.warning(`Could not read CI artifact ${artifact.id}: ${error.message}`);
    return null;
  } finally {
    fs.rmSync(archivePath, { force: true });
  }
}

function coverageSummary({ artifacts, core, owner, repo, run }) {
  const summaryArtifact = artifacts.find(
    ({ name, expired }) => name.startsWith("coverage-summary-") && !expired,
  );
  if (!summaryArtifact) {
    return "";
  }
  const contents = readArtifactFile({
    artifact: summaryArtifact,
    core,
    filename: "coverage-summary.json",
    maxChars: 1024 * 1024,
    owner,
    repo,
  });
  if (!contents) {
    return "";
  }
  try {
    const summary = JSON.parse(contents);
    const totals = summary.total || summary.totals;
    const percentage = Number(
      totals?.lines?.pct ?? totals?.percent_covered_display,
    );
    if (!Number.isFinite(percentage) || percentage < 0 || percentage > 100) {
      throw new Error("missing total line coverage");
    }
    const formattedPercentage = percentage
      .toFixed(2)
      .replace(/\.00$/, "")
      .replace(/(\.\d)0$/, "$1");
    const reportArtifact = artifacts.find(
      ({ name, expired }) => name.startsWith("coverage-report-") && !expired,
    );
    const reportLink = reportArtifact
      ? ` | [download coverage report](${artifactUrl(
          owner,
          repo,
          run,
          reportArtifact,
        )})`
      : "";
    return ` | Coverage: **${formattedPercentage}%** lines${reportLink}`;
  } catch (error) {
    core.warning(
      `Could not parse coverage artifact ${summaryArtifact.id}: ${error.message}`,
    );
    return "";
  }
}

function formattingDiffDetails(name, diff) {
  if (!diff) {
    return "";
  }
  const backtickRuns = diff.match(/`+/g) || [];
  const longestRun = Math.max(0, ...backtickRuns.map((run) => run.length));
  const fence = "`".repeat(Math.max(3, longestRun + 1));
  return [
    "",
    "",
    "<details>",
    `<summary>Formatting diff for ${name}</summary>`,
    "",
    `${fence}diff`,
    diff,
    fence,
    "",
    "</details>",
  ].join("\n");
}

function cleanStepName(name) {
  return name.replace(/[\r\n]+/g, " ").replace(/[\\`*_[\]<>]/g, "\\$&");
}

module.exports = async function reportCi({ core, context, github }) {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const trigger = context.payload.workflow_run;

  let pull = trigger.pull_requests[0];
  if (!pull) {
    const response =
      await github.rest.repos.listPullRequestsAssociatedWithCommit({
        owner,
        repo,
        commit_sha: trigger.head_sha,
      });
    pull = response.data.find(
      ({ base, head, state }) =>
        state === "open" &&
        head.sha === trigger.head_sha &&
        base.repo?.full_name === `${owner}/${repo}`,
    );
  }
  if (!pull) {
    core.notice(`No open PR found for workflow run ${trigger.id}`);
    return;
  }

  const response = await github.rest.actions.listWorkflowRunsForRepo({
    owner,
    repo,
    event: "pull_request",
    head_sha: trigger.head_sha,
    per_page: 100,
  });
  const runs = new Map();
  for (const run of response.data.workflow_runs) {
    if (WORKFLOW_NAMES.has(run.name) && !runs.has(run.name)) {
      runs.set(run.name, run);
    }
  }

  const failed = [];
  const pending = [];
  let buildResult = "The site build has not started.";
  const results = new Map();
  for (const [name, run] of runs) {
    const runLink = `[logs](${run.html_url})`;
    if (run.status !== "completed") {
      pending.push(name);
      results.set(name, `- ⏳ **${name}** is running. ${runLink}`);
      continue;
    }

    const artifacts = await github.paginate(
      github.rest.actions.listWorkflowRunArtifacts,
      { owner, repo, run_id: run.id, per_page: 100 },
    );
    if (name === "Build" && run.conclusion === "success") {
      const artifact = artifacts.find(
        ({ name, expired }) => name === `pr-${pull.number}-site` && !expired,
      );
      buildResult = artifact
        ? `✅ Site built successfully. [Download rendered site](${artifactUrl(
            owner,
            repo,
            run,
            artifact,
          )}) | ${runLink}`
        : `⚠️ Site built, but its artifact is unavailable. ${runLink}`;
    } else if (name === "Build") {
      buildResult = `❌ Site build ${run.conclusion}. ${runLink}`;
    }

    const icon =
      run.conclusion === "success"
        ? "✅"
        : run.conclusion === "skipped"
          ? "⏭️"
          : "❌";
    const coverage = coverageSummary({ artifacts, core, owner, repo, run });
    results.set(
      name,
      `- ${icon} **${name}** ${run.conclusion}. ${runLink}${coverage}`,
    );

    if (run.conclusion !== "success" && run.conclusion !== "skipped") {
      const jobs = await github.paginate(
        github.rest.actions.listJobsForWorkflowRun,
        { owner, repo, run_id: run.id, per_page: 100 },
      );
      const steps = jobs
        .flatMap((job) => job.steps || [])
        .filter(({ conclusion }) => conclusion === "failure")
        .map(({ name }) => cleanStepName(name));
      const diffArtifact = artifacts.find(
        ({ name, expired }) => name.startsWith("formatting-diff-") && !expired,
      );
      const details = steps.length ? ` - ${steps.join(", ")}` : "";
      const diffLink = diffArtifact
        ? ` | [download formatting diff](${artifactUrl(
            owner,
            repo,
            run,
            diffArtifact,
          )})`
        : "";
      const fixCommand = FORMAT_COMMANDS.get(name);
      const fix =
        diffArtifact && fixCommand ? ` | Fix with \`${fixCommand}\`` : "";
      const inlineDiff = readArtifactFile({
        artifact: diffArtifact,
        core,
        filename: "formatting.diff",
        maxChars: 6000,
        owner,
        repo,
      });
      failed.push(
        `- **${name}**${details} | ${runLink}${diffLink}${fix}` +
          formattingDiffDetails(name, inlineDiff),
      );
    }
  }

  const lines = [
    MARKER,
    "### CI report",
    "",
    `Commit \`${trigger.head_sha.slice(0, 7)}\``,
    "",
    "#### Build",
    "",
    buildResult,
  ];
  const sections = [
    ["Frontend", ["Check - Frontend"]],
    ["Python", ["Check - Python", "Test - Scripts", "Test - Updater"]],
    [
      "Other checks",
      [
        "Check - Assets",
        "Check - Content and Data",
        "Check - Discord",
        "Check - Makefile",
        "Check - Templates",
        "Check - YAML",
      ],
    ],
  ];
  for (const [heading, names] of sections) {
    const sectionResults = names.flatMap((name) =>
      results.has(name) ? [results.get(name)] : [],
    );
    lines.push("", `#### ${heading}`, "");
    lines.push(
      ...(sectionResults.length
        ? sectionResults
        : [
            `No matching ${heading.toLowerCase()} workflow ran for this change.`,
          ]),
    );
  }
  if (failed.length) {
    lines.push("", "#### Failures", "", ...failed);
  }
  if (!failed.length && !pending.length) {
    lines.push("", "✅ All completed checks passed.");
  }
  if (pending.length) {
    lines.push("", `⏳ Waiting for: ${pending.join(", ")}`);
  }
  const body = lines.join("\n");

  const comments = await github.paginate(github.rest.issues.listComments, {
    owner,
    repo,
    issue_number: pull.number,
    per_page: 100,
  });
  // Bot PR comments are sticky: identify ours by marker and update it.
  const existing = comments.find(
    ({ body, user }) =>
      user?.id === 41898282 &&
      user.login === "github-actions[bot]" &&
      body?.includes(MARKER),
  );
  if (existing) {
    await github.rest.issues.updateComment({
      owner,
      repo,
      comment_id: existing.id,
      body,
    });
  } else {
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: pull.number,
      body,
    });
  }
};
