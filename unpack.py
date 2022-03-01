import os
import os.path
import sys
import tarfile
import tempfile
from subprocess import Popen

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
print(f"Building file diffs in {diff_dir}")

snapshots = os.listdir(dest_dir)
pairs = list(zip(snapshots, snapshots[1:] + snapshots[:1]))

for (first, second) in pairs:
  first_dir = os.path.join(dest_dir, first)
  second_dir = os.path.join(dest_dir, second)

  for filename in found_files:
    # Diff for json/yaml files only
    if not filename.endswith(".json") and not filename.endswith(".yaml"):
      continue

    # Skip diff if either of files doesn't exist
    first_path = os.path.join(first_dir, filename)
    if not os.path.isfile(first_path):
      continue
    second_path = os.path.join(second_dir, filename)
    if not os.path.isfile(second_path):
      continue
    cmdline = ["dyff", "between", "--omit-header", first_path, second_path]
    # Save file diff for foo/bar/baz.yaml to foo/bar/hash1_hash2_baz.yaml
    diff_filename = f"{first}_{second}_{os.path.basename(filename)}.diff"
    diff_location = os.path.join(diff_dir, os.path.dirname(filename))
    try:
      os.makedirs(diff_location)
    except FileExistsError:
      pass
    diff_path = os.path.join(diff_location, diff_filename)
    diff_file = open(diff_path, "w")
    proc = Popen(cmdline, stdout=diff_file)
    out, err = proc.communicate()

    if os.path.getsize(diff_path) == 0:
      os.remove(diff_path)

print("Cleaning up empty dirs")
walk = list(os.walk(diff_dir))
for path, _, _ in walk[::-1]:
    if len(os.listdir(path)) == 0:
        os.rmdir(path)

print("Starting loki container")
out, err = Popen(["docker", "rm", "-f", "loki"]).communicate()
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
Popen(cmdline).communicate()

print("Starting grafana container")
out, err = Popen(["docker", "rm", "-f", "grafana"]).communicate()
cmdline = [
  "docker", "run", "-d", "--name=grafana",
  "-p=3000:3000",
  "-ti", "docker.io/grafana/grafana:8.4.2"
]
Popen(cmdline).communicate()
