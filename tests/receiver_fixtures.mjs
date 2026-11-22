import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export function receiverFixture(kind) {
  const cwd = fileURLToPath(new URL("../", import.meta.url));
  const python = process.env.QFS_TEST_PYTHON || (process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python");
  return JSON.parse(execFileSync(python, ["-m", "tests.receiver_fixtures", kind], {
    cwd, encoding: "utf8",
  }));
}
