import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export function runTestPython(args) {
  const cwd = fileURLToPath(new URL("../", import.meta.url));
  const python = process.env.QFS_TEST_PYTHON || (process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python");
  return execFileSync(python, args, { cwd, encoding: "utf8" });
}

export function receiverFixture(kind) {
  return JSON.parse(runTestPython(["-m", "tests.receiver_fixtures", kind]));
}
