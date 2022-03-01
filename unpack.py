import os
import os.path
import sys
import tarfile
import tempfile
import json
import hashlib
from subprocess import run

if len(sys.argv) < 2:
  print("Usage: unpack.py <directory>")
  sys.exit(1)

src_dir = os.path.abspath(sys.argv[1])

dest_dir = tempfile.mkdtemp()
yamls_dir = os.path.join(dest_dir, "yamls")

print(f"Unpacking to {yamls_dir}")
os.makedirs(yamls_dir)

found_files = set([])

for filename in os.listdir(src_dir):
  filepath = os.path.join(src_dir, filename)
  if not os.path.isfile(filepath):
    continue

  file = tarfile.open(filepath)
  archive_contents = set(file.getnames())
  found_files.update(archive_contents)

  file.extractall(os.path.join(yamls_dir, filename))
  file.close()

diff_dir = os.path.join(dest_dir, "diffs")
os.makedirs(diff_dir)

print("Starting loki container")
run(["docker", "rm", "-f", "loki"])
lokiconfig_dir = os.path.abspath(os.path.join(os.getcwd(), "lokiconfig"))
lokidata_dir = os.path.join(dest_dir, "loki")
os.makedirs(lokidata_dir)
cmdline = [
  "docker", "run", "-d", "--name=loki", "-u=0",
  f"-v={lokiconfig_dir}:/etc/loki:z",
  f"-v={lokidata_dir}:/srv/loki:z",
  "-p=3100:3100",
  "-ti", "docker.io/grafana/loki:2.4.0"
]
run(cmdline)

print("Starting grafana container")
run(["docker", "rm", "-f", "grafana"])
cmdline = [
  "docker", "run", "-d", "--name=grafana",
  "-p=3000:3000",
  "-ti", "docker.io/grafana/grafana:8.4.2"
]
run(cmdline)

print("Starting promtail container")
run(["docker", "rm", "-f", "promtail"])
promtailconfig_dir = os.path.abspath(os.path.join(os.getcwd(), "promtailconfig"))
promtaildata_dir = os.path.join(dest_dir, "promtail")
os.makedirs(promtaildata_dir)
cmdline = [
  "docker", "run", "-d", "--name=promtail",
  f"-v={promtailconfig_dir}:/etc/promtail:z",
  f"-v={diff_dir}:/tmp/log:z",
  f"-v={promtaildata_dir}:/run/promtail:z",
  "-ti", "docker.io/grafana/promtail:2.4.0"
]
run(cmdline)

print(f"Building file diffs in {diff_dir}")

snapshots = sorted(os.listdir(yamls_dir))
pairs = list(zip(snapshots, snapshots[1:] + snapshots[:1]))

diff_path = os.path.join(diff_dir, "diffs.log")
with open(diff_path, "w") as f:
  for (first, second) in pairs:
    first_dir = os.path.join(yamls_dir, first)
    second_dir = os.path.join(yamls_dir, second)

    for filename in found_files:
      # Diff for json/yaml files only
      if not filename.endswith(".json") and not filename.endswith(".yaml"):
        continue

      # Skip diff if either of files doesn't exist
      first_path = os.path.join(first_dir, filename)
      second_path = os.path.join(second_dir, filename)
      if not os.path.isfile(first_path) or not os.path.isfile(second_path):
        continue
      cmdline = ["dyff", "between", "--omit-header", first_path, second_path]

      proc = run(cmdline, capture_output=True)
      diff_output = proc.stdout.decode("utf-8")
      if len(diff_output) == 0:
        continue

      for stanza in diff_output.strip().split("\n\n"):
        # Store output into json
        # TODO convert snapshot into date
        data = {
          "file": filename,
          "snapshot": second,
          "diff": line,
        }
        f.write(json.dumps(stanza))
        f.write("\n")

print("Cleaning up empty dirs")
walk = list(os.walk(diff_dir))
for path, _, _ in walk[::-1]:
    if len(os.listdir(path)) == 0:
        os.rmdir(path)
