---
name: generate-minecraft-k8s-manifest
description: Generate commented Kubernetes Deployment, Service, and optional PersistentVolumeClaim manifests for Minecraft servers operated on the Azisaba Network. Use when Codex is asked to create, draft, or revise an アジ鯖 Minecraft server manifest based on the AzisabaNetwork/minecraft-servers conventions, including itzg/minecraft-server settings, Kuvel discovery labels, Java selection, resources, hostPath or nfs-client PVC storage, TAB ConfigMap mounting, and optional ports or environment variables.
---

# Generate Minecraft K8s Manifest

Generate an Azisaba-specific Minecraft server manifest after collecting only
the information missing from the user's request.

## Gather Missing Values

Extract every value already present in the request. Ask only for missing
values, grouped into one concise message rather than asking one question at a
time.

Collect these required values:

- Server name
- Minecraft version
- Server type: suggest `PAPER` or `FOLIA`, but accept another
  `itzg/minecraft-server` type as free-form input
- Heap size for `MEMORY`, expressed as a positive whole number of GiB
- Storage mode: `hostPath` or PVC

For `hostPath`, also collect:

- `nodeName`, such as `saba12`
- Host path; propose `/srv/{server-name}` when the user is unsure
- GID

For PVC, also collect:

- Requested storage capacity; always ask for it and propose `30Gi` when the
  user is unsure
- Whether `nfs-client` is acceptable as the StorageClass; use the user's
  replacement when it is not

Ask whether to mount the default TAB ConfigMap
`common-life-server-tab-config`. Do not mount it when the user declines.

Ask in the same grouped message whether any of these optional settings are
needed:

- Additional environment variables
- `JVM_OPTS`
- `JVM_DD_OPTS`
- Additional container and Service ports
- Additional volumes and volume mounts
- Overrides for the automatically derived Java image or Kubernetes resources

Do not ask for values that have fixed defaults in
[references/azisaba-conventions.md](references/azisaba-conventions.md).

## Resolve Defaults

Read [references/azisaba-conventions.md](references/azisaba-conventions.md)
before generating a manifest.

Derive the Java version from the Minecraft version. If the version cannot be
classified confidently, ask for a Java version instead of guessing.

Derive resources from heap unless the user provides overrides:

- CPU request: `500m`
- CPU limit: `5000m`
- Memory request: the same numeric GiB value as heap
- Memory limit: heap plus `4Gi`

Use UID `0`. For PVC use GID `1000`. For `hostPath`, use the GID supplied by
the user.

## Generate The Base Manifest

Tell the user that the generated manifest contains `EULA: "true"` before
showing it. Do not repeatedly ask for a separate confirmation.

Use the bundled generator for the base Deployment, Service, and optional PVC:

```bash
python3 scripts/generate_manifest.py \
  --server-name example \
  --minecraft-version 1.21.4 \
  --server-type PAPER \
  --heap-gib 8 \
  --storage-mode pvc \
  --pvc-capacity 30Gi \
  --storage-class nfs-client \
  --use-tab-config
```

Run the script from the skill directory, or use its absolute path. Pass
explicit resource overrides only when supplied by the user. Use
`--java-version` only when overriding automatic selection.

Use repeatable `--extra-env NAME=VALUE` and
`--extra-port NAME:PORT[:TARGET_PORT]` arguments when requested. Pass
`--jvm-opts` and `--jvm-dd-opts` when supplied.

For additional volumes or volume mounts that the generator does not model,
modify the generated YAML carefully after generation. Keep names consistent
between `volumeMounts` and `volumes`. Do not invent a source type or path;
collect any missing details first.

## Check The Result

Before responding:

- Confirm every selector matches the pod labels.
- Confirm the Kuvel preferred server name equals the requested server name.
- Confirm the image Java version matches the selected Java version.
- Confirm memory request is not below heap and memory limit is above heap.
- Confirm `hostPath` includes `nodeName`, path, and user-provided GID.
- Confirm PVC uses `ReadWriteMany`, includes the requested capacity, and uses
  the confirmed StorageClass.
- Confirm every Service port has a matching container port.
- Confirm every volume mount has a corresponding volume.
- Preserve string quoting for Minecraft versions and Kubernetes quantities.

If `kubectl` is available, validate without changing cluster state:

```bash
kubectl apply --dry-run=client -f <manifest-file>
```

Do not require `kubectl` to be installed. Perform the structural checks above
when it is unavailable.

## Present Or Save

By default, show the complete manifest in a fenced `yaml` block and do not
write it to disk.

Save the manifest only when the user explicitly asks. When saving, ask for the
destination only if it is missing, preserve unrelated files, and report the
written path.

Keep explanatory Japanese comments in the YAML, especially around Java
selection, heap versus Kubernetes memory, storage behavior, probes, and
fixed Azisaba settings.
