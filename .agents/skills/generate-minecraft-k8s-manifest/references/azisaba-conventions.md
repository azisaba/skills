# Azisaba Minecraft Kubernetes Conventions

Use these defaults for manifests modeled after
`AzisabaNetwork/minecraft-servers`.

Source: `https://github.com/AzisabaNetwork/minecraft-servers`, inspected at
commit `08960780121da67adc9b2cc347fa2e8bb505bfbd`. Treat the rules in this
reference as the Skill's stable defaults. Inspect the upstream repository
again only when the user explicitly requests synchronization with newer
conventions.

## Fixed Workload Settings

- Workload kind: `Deployment`
- Update strategy: `Recreate`
- Revision history: `2`
- Container image: `itzg/minecraft-server:java{java-version}`
- Working directory: `/data`
- Image pull policy: `Always`
- Container and Service Minecraft port: `25565`
- Service type: `ClusterIP`
- PriorityClass: `minecraft-other-server`
- Termination grace period: `60` seconds
- Namespace: omit

Use this startup probe:

```yaml
startupProbe:
  tcpSocket:
    port: 25565
  failureThreshold: 60
  periodSeconds: 10
```

## Java Selection

Select the Java image from the Minecraft version:

| Minecraft version | Java |
| --- | ---: |
| 1.14.4 and earlier | 8 |
| 1.15.x | 11 |
| 1.16.x | 11 |
| 1.17.x | 17 |
| 1.18.x through 1.20.4 | 17 |
| 1.20.5 through 1.21.x | 21 |
| 26.1 and later | 25 |

Ask for an explicit Java version when a version falls outside these ranges or
cannot be parsed confidently.

## Labels

Always add:

```yaml
app: server-{server-name}
stage: production
kuvel.azisaba.net/enable-server-discovery: "true"
kuvel.azisaba.net/preferred-server-name: {server-name}
kuvel.azisaba.net/disable-load-balancer: "true"
kuvel.azisaba.net/disable-name-suffix: "true"
```

The Service selector uses only:

```yaml
app: server-{server-name}
stage: production
```

## Environment

Always add:

- `TZ="Asia/Tokyo"`
- `EULA="true"`
- `TYPE` from the user's server type
- `USE_AIKAR_FLAGS="true"`
- `UID="0"`
- `GID`: user-supplied for `hostPath`, otherwise `"1000"`
- `VERSION`: quote the Minecraft version
- `MEMORY`: heap as `{n}G`
- `ENV_VARIABLE_PREFIX="CFG_"`

Always expose pod metadata through:

- `CFG_POD_NAME`
- `CFG_POD_NAMESPACE`
- `CFG_SERVER_NAME`
- `POD_NAME`
- `POD_NAMESPACE`
- `SERVER_NAME`

Resolve server-name variables from
`metadata.labels['kuvel.azisaba.net/preferred-server-name']`.

Do not add `JVM_OPTS` or `JVM_DD_OPTS` unless the user requests them.

## Resources

When the user only specifies heap:

- CPU request: `500m`
- CPU limit: `5000m`
- Memory request: `{heap}Gi`
- Memory limit: `{heap + 4}Gi`

Allow explicit overrides. Reject a memory request below heap or a memory limit
at or below heap unless the user clearly understands and insists on it.

## Storage

Mount server data at `/data`.

For `hostPath`:

- Require `nodeName`.
- Propose `/srv/{server-name}`.
- Use `type: Directory`.
- Require a GID.

For PVC:

- Omit `nodeName` by default.
- Claim name: `server-{server-name}-data-claim`
- Default StorageClass proposal: `nfs-client`
- AccessMode: always `ReadWriteMany`
- Always ask for capacity; propose `30Gi` when uncertain.
- GID: `1000`

## TAB ConfigMap

Ask whether to mount the default `common-life-server-tab-config`.

When enabled:

```yaml
volumeMounts:
  - name: tab-config
    mountPath: /plugins/TAB/config.yml
    subPath: config.yml
volumes:
  - name: tab-config
    configMap:
      name: common-life-server-tab-config
```

Allow the user to supply a different ConfigMap name if explicitly requested.

## Output

Display YAML by default. Write a file only on explicit request. Include
Japanese comments explaining non-obvious or operationally important settings.
