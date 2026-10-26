#!/usr/bin/env node
// vibelabs-sdlc 설치기: `npx github:vibelabs-web/vibelabs-native-sdlc`
//
// 기본은 Claude Code 플러그인 설치(`claude plugin marketplace add` → `claude plugin install`).
// `claude` 명령이 없거나 --copy 면 하네스를 ~/.claude/vibelabs-sdlc 로 복사하고 스킬·에이전트를 심링크한다.
// 기존 파일이나 다른 곳을 가리키는 심링크는 덮어쓰지 않는다 (install.sh 와 같은 규칙).
// 외부 의존성 없음 — Node 표준 모듈만 쓴다.
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const PKG_ROOT = path.resolve(__dirname, "..");
const PKG = JSON.parse(fs.readFileSync(path.join(PKG_ROOT, "package.json"), "utf8"));
const MARKETPLACE = "vibelabs-sdlc";
const PLUGIN_ID = `vibelabs-sdlc@${MARKETPLACE}`;
const DEFAULT_SOURCE = "vibelabs-web/vibelabs-native-sdlc";
const MARKER = ".vibelabs-sdlc-install";
// 복사 모드에서 사용자에게 필요한 것만 옮긴다 (tests·.github 제외)
const COPY_ITEMS = ["skills", "agents", "scripts", "schemas", "templates", "docs", "evals", "examples",
  ".claude-plugin", "install.sh", "LICENSE", "README.md", "package.json"];

const HELP = `vibelabs-sdlc ${PKG.version} — AI-Native SDLC 하네스 설치

사용법: npx github:${DEFAULT_SOURCE} [옵션]

  (옵션 없음)         Claude Code 플러그인으로 설치·업데이트 (claude 가 없으면 복사 설치)
  --scope <s>         플러그인 범위: user(기본) · project · local
  --copy              플러그인 대신 ~/.claude/vibelabs-sdlc 에 복사하고 스킬·에이전트 심링크
  --source <repo>     마켓플레이스 소스 (기본 ${DEFAULT_SOURCE}, 브랜치는 owner/repo#ref)
  --check             설치 상태만 출력 (변경 없음)
  --remove            이 설치기가 만든 것만 제거 (플러그인 제거 + 복사본·심링크 제거)
  -v, --version       버전
  -h, --help          도움말

요구 사항: Python 3.10+, git. 설치 후 Claude Code 를 재시작하고 /vibelabs-sdlc:sdlc (복사 설치는 /sdlc) 로 시작.`;

function parseArgs(argv) {
  const o = { mode: "install", scope: "user", copy: false, source: DEFAULT_SOURCE };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) fail(`${a} 에 값이 필요함`, 2);
      return argv[++i];
    };
    if (a === "-h" || a === "--help") o.mode = "help";
    else if (a === "-v" || a === "--version") o.mode = "version";
    else if (a === "--check") o.mode = "check";
    else if (a === "--remove") o.mode = "remove";
    else if (a === "--copy") o.copy = true;
    else if (a === "--scope") o.scope = next();
    else if (a === "--source") o.source = next();
    else fail(`알 수 없는 옵션: ${a}`, 2);
  }
  if (!["user", "project", "local"].includes(o.scope)) fail(`--scope 는 user·project·local 중 하나: ${o.scope}`, 2);
  return o;
}

function fail(msg, code = 1) {
  console.error(`오류: ${msg}`);
  process.exit(code);
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { encoding: "utf8", ...opts });
  return { ok: r.status === 0 && !r.error, status: r.status, stdout: r.stdout || "", stderr: r.stderr || "", error: r.error };
}

function claudeDir() {
  return process.env.VIBELABS_SDLC_CLAUDE_DIR || path.join(os.homedir(), ".claude");
}

// ------------------------------------------------------------------ 요구 사항

function checkPrereqs() {
  const problems = [];
  const py = run("python3", ["-c", "import sys;print('%d.%d'%sys.version_info[:2])"]);
  if (!py.ok) problems.push("python3 없음 — Python 3.10+ 필요");
  else {
    const [maj, min] = py.stdout.trim().split(".").map(Number);
    if (maj < 3 || (maj === 3 && min < 10)) problems.push(`Python ${py.stdout.trim()} — 3.10+ 필요`);
  }
  if (!run("git", ["--version"]).ok) problems.push("git 없음");
  return problems;
}

function hasClaude() {
  return run("claude", ["--version"]).ok;
}

// ------------------------------------------------------------------ 플러그인 모드

function claudeJson(args) {
  const r = run("claude", [...args, "--json"]);
  if (!r.ok) return null;
  try {
    return JSON.parse(r.stdout);
  } catch {
    return null;
  }
}

function claudeStep(args) {
  console.log(`$ claude ${args.join(" ")}`);
  const r = run("claude", args, { stdio: "inherit" });
  if (!r.ok) fail(`claude ${args.join(" ")} 실패 (exit ${r.status})`);
}

function pluginInstall(o) {
  const mkts = claudeJson(["plugin", "marketplace", "list"]) || [];
  if (mkts.some((m) => m.name === MARKETPLACE)) claudeStep(["plugin", "marketplace", "update", MARKETPLACE]);
  else claudeStep(["plugin", "marketplace", "add", o.source]);
  const plugins = claudeJson(["plugin", "list"]) || [];
  const have = plugins.some((p) => p.id === PLUGIN_ID && p.scope === o.scope);
  claudeStep(["plugin", have ? "update" : "install", PLUGIN_ID, "--scope", o.scope]);
  console.log(`\n완료 — Claude Code 를 재시작하고 /vibelabs-sdlc:sdlc 로 시작하세요.`);
}

function pluginStatus() {
  if (!hasClaude()) return "claude 명령 없음";
  const p = (claudeJson(["plugin", "list"]) || []).filter((x) => x.id === PLUGIN_ID);
  return p.length ? p.map((x) => `${x.version} (${x.scope}${x.enabled ? "" : ", 비활성"})`).join(", ") : "미설치";
}

// ------------------------------------------------------------------ 복사 모드

function copyLinks(home) {
  const links = [];
  const skillsSrc = path.join(home, "skills");
  for (const n of fs.readdirSync(skillsSrc).filter((n) => n.startsWith("sdlc")).sort())
    links.push([path.join(claudeDir(), "skills", n), path.join(skillsSrc, n), "dir"]);
  const agentsSrc = path.join(home, "agents");
  for (const n of fs.readdirSync(agentsSrc).filter((n) => /^sdlc-.*\.md$/.test(n)).sort())
    links.push([path.join(claudeDir(), "agents", n), path.join(agentsSrc, n), "file"]);
  return links;
}

function linkTarget(p) {
  try {
    return fs.readlinkSync(p);
  } catch {
    return null;
  }
}

function exists(p) {
  try {
    fs.lstatSync(p);
    return true;
  } catch {
    return false;
  }
}

function copyInstall() {
  const home = path.join(claudeDir(), "vibelabs-sdlc");
  if (exists(home) && !exists(path.join(home, MARKER)))
    fail(`${home} 가 이미 있고 이 설치기가 만든 것이 아님 — 덮어쓰지 않음`);
  // 먼저 충돌을 모두 확인하고, 하나라도 있으면 아무것도 바꾸지 않는다
  const tmpLinks = copyLinks(PKG_ROOT).map(([dest, src, kind]) => [dest, path.join(home, path.relative(PKG_ROOT, src)), kind]);
  const conflicts = tmpLinks.filter(([dest, src]) => exists(dest) && linkTarget(dest) !== src).map(([d]) => d);
  if (conflicts.length) fail(`기존 항목이 있어 중단 (덮어쓰지 않음):\n  ${conflicts.join("\n  ")}`);

  fs.rmSync(home, { recursive: true, force: true });
  fs.mkdirSync(home, { recursive: true });
  for (const item of COPY_ITEMS) {
    const src = path.join(PKG_ROOT, item);
    if (exists(src)) fs.cpSync(src, path.join(home, item), { recursive: true, filter: (s) => !s.includes("__pycache__") });
  }
  fs.writeFileSync(path.join(home, MARKER), `${PKG.version}\n`);
  for (const [dest, src, kind] of tmpLinks) {
    if (linkTarget(dest) === src) continue;
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.symlinkSync(src, dest, process.platform === "win32" && kind === "dir" ? "junction" : kind);
    console.log(`등록    ${dest} -> ${src}`);
  }
  console.log(`\n완료 — ${home} (${PKG.version}). Claude Code 를 재시작하고 /sdlc 로 시작하세요.`);
}

function copyStatus() {
  const home = path.join(claudeDir(), "vibelabs-sdlc");
  if (!exists(path.join(home, MARKER))) return { text: "미설치", links: [] };
  const ver = fs.readFileSync(path.join(home, MARKER), "utf8").trim();
  const links = copyLinks(home).map(([dest, src]) => {
    const cur = linkTarget(dest);
    return `${cur === src ? "OK      " : exists(dest) ? "CONFLICT" : "MISSING "} ${dest}`;
  });
  return { text: `${ver} (${home})`, links };
}

function copyRemove() {
  const home = path.join(claudeDir(), "vibelabs-sdlc");
  if (!exists(path.join(home, MARKER))) return false;
  for (const [dest, src] of copyLinks(home)) {
    if (linkTarget(dest) === src) {
      fs.unlinkSync(dest);
      console.log(`제거    ${dest}`);
    }
  }
  fs.rmSync(home, { recursive: true, force: true });
  console.log(`제거    ${home}`);
  return true;
}

// ------------------------------------------------------------------ main

function main() {
  const o = parseArgs(process.argv.slice(2));
  if (o.mode === "help") return console.log(HELP);
  if (o.mode === "version") return console.log(PKG.version);

  if (o.mode === "check") {
    const c = copyStatus();
    console.log(`플러그인: ${pluginStatus()}`);
    console.log(`복사 설치: ${c.text}`);
    c.links.forEach((l) => console.log(`  ${l}`));
    const problems = checkPrereqs();
    console.log(`요구 사항: ${problems.length ? problems.join(" · ") : "OK (python3 3.10+, git)"}`);
    return;
  }

  if (o.mode === "remove") {
    let any = copyRemove();
    if (hasClaude() && (claudeJson(["plugin", "list"]) || []).some((p) => p.id === PLUGIN_ID && p.scope === o.scope)) {
      claudeStep(["plugin", "uninstall", PLUGIN_ID, "--scope", o.scope]);
      any = true;
    }
    if (!any) console.log("제거할 것 없음");
    return;
  }

  const problems = checkPrereqs();
  if (problems.length) console.warn(`경고: ${problems.join(" · ")} — 설치는 하지만 하네스 CLI 실행에 필요합니다.`);
  if (!o.copy && hasClaude()) return pluginInstall(o);
  if (!o.copy) console.log("claude 명령이 없어 복사 설치로 진행합니다 (--copy).");
  copyInstall();
}

main();
