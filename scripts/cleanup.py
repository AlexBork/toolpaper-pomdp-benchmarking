import sys, os
from collections import OrderedDict

# Replacements will be applied in this order
REPLACEMENTS = OrderedDict()
REPLACEMENTS["/rwthfs/rz/cluster/home/ab129254/git/storm-pomdp-benchmarking/"] = "$BENCH_HOME/"

if len(sys.argv) != 2:
    print("Usage: python3 cleanup.py <directory>")
    exit(1)
print("Cleaning up directory '{}'.".format(sys.argv[1]))
directory = sys.argv[1]
if not os.path.isdir(directory):
    print("Directory '{}' does not exist.".format(directory))
    exit(1)

print("WARN: This is fumbling with your files. It's probably a good time to make a backup.")
input("Press Enter to continue or Ctrl+C to abort.")


for file in os.listdir(directory):
    # open file and apply replacement
    with open(os.path.join(directory, file), 'r') as f:
        content = f.read()
        for old, new in REPLACEMENTS.items():
            content = content.replace(old, new)
    # write file back
    with open(os.path.join(directory, file), 'w') as f:
        f.write(content)
print("Done.")