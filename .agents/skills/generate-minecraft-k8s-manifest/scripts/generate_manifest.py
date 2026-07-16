#!/usr/bin/env python3
"""Generate an Azisaba-style Minecraft Kubernetes manifest."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass


DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
QUANTITY = re.compile(r"^[1-9][0-9]*(?:m|Mi|Gi)?$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PORT_NAME = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")


@dataclass(frozen=True)
class ExtraPort:
    name: str
    port: int
    target_port: int


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Generate an Azisaba Minecraft Deployment, Service, and optional PVC."
    )
    result.add_argument("--server-name", required=True)
    result.add_argument("--minecraft-version", required=True)
    result.add_argument("--server-type", required=True)
    result.add_argument("--heap-gib", required=True, type=positive_int)
    result.add_argument("--storage-mode", required=True, choices=("hostpath", "pvc"))
    result.add_argument("--java-version", choices=("8", "11", "17", "21", "25"))
    result.add_argument("--node-name")
    result.add_argument("--host-path")
    result.add_argument("--gid")
    result.add_argument("--pvc-capacity")
    result.add_argument("--storage-class", default="nfs-client")
    result.add_argument("--tab-config-name", default="common-life-server-tab-config")
    result.add_argument("--use-tab-config", action="store_true")
    result.add_argument("--cpu-request", default="500m")
    result.add_argument("--cpu-limit", default="5000m")
    result.add_argument("--memory-request")
    result.add_argument("--memory-limit")
    result.add_argument("--jvm-opts")
    result.add_argument("--jvm-dd-opts")
    result.add_argument("--extra-env", action="append", default=[], metavar="NAME=VALUE")
    result.add_argument(
        "--extra-port",
        action="append",
        default=[],
        metavar="NAME:PORT[:TARGET_PORT]",
    )
    return result


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive whole number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive whole number")
    return parsed


def parse_minecraft_version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", value):
        raise ValueError(
            f"cannot classify Minecraft version {value!r}; pass --java-version explicitly"
        )
    return tuple(int(part) for part in value.split("."))


def select_java(value: str) -> str:
    version = parse_minecraft_version(value)
    major = version[0]
    minor = version[1]
    patch = version[2] if len(version) > 2 else 0

    if major > 26 or (major == 26 and minor >= 1):
        return "25"
    if major != 1:
        raise ValueError(
            f"cannot classify Minecraft version {value!r}; pass --java-version explicitly"
        )
    if minor < 14 or (minor == 14 and patch <= 4):
        return "8"
    if minor in (15, 16):
        return "11"
    if minor == 17:
        return "17"
    if 18 <= minor <= 19:
        return "17"
    if minor == 20:
        return "17" if patch <= 4 else "21"
    if minor == 21:
        return "21"
    raise ValueError(
        f"cannot classify Minecraft version {value!r}; pass --java-version explicitly"
    )


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_env(values: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    reserved = {
        "TZ",
        "EULA",
        "TYPE",
        "USE_AIKAR_FLAGS",
        "UID",
        "GID",
        "VERSION",
        "MEMORY",
        "ENV_VARIABLE_PREFIX",
        "CFG_POD_NAME",
        "CFG_POD_NAMESPACE",
        "CFG_SERVER_NAME",
        "POD_NAME",
        "POD_NAMESPACE",
        "SERVER_NAME",
    }
    for item in values:
        if "=" not in item:
            raise ValueError(f"invalid --extra-env {item!r}; expected NAME=VALUE")
        name, value = item.split("=", 1)
        if not ENV_NAME.fullmatch(name):
            raise ValueError(f"invalid environment variable name {name!r}")
        if name in reserved:
            raise ValueError(f"{name!r} is managed by the generator")
        result.append((name, value))
    return result


def parse_ports(values: list[str]) -> list[ExtraPort]:
    result: list[ExtraPort] = []
    seen_names = {"minecraft"}
    seen_container_ports = {25565}
    for item in values:
        pieces = item.split(":")
        if len(pieces) not in (2, 3):
            raise ValueError(
                f"invalid --extra-port {item!r}; expected NAME:PORT[:TARGET_PORT]"
            )
        name = pieces[0]
        if len(name) > 15 or not PORT_NAME.fullmatch(name):
            raise ValueError(f"invalid Service port name {name!r}")
        if name in seen_names:
            raise ValueError(f"duplicate Service port name {name!r}")
        try:
            port = int(pieces[1])
            target = int(pieces[2]) if len(pieces) == 3 else port
        except ValueError as exc:
            raise ValueError(f"invalid numeric port in {item!r}") from exc
        for candidate in (port, target):
            if not 1 <= candidate <= 65535:
                raise ValueError(f"port out of range in {item!r}")
        if target in seen_container_ports:
            raise ValueError(f"duplicate container port {target}")
        seen_names.add(name)
        seen_container_ports.add(target)
        result.append(ExtraPort(name=name, port=port, target_port=target))
    return result


def validate(args: argparse.Namespace) -> tuple[str, str, str, list[tuple[str, str]], list[ExtraPort]]:
    if len(args.server_name) > 63 or not DNS_LABEL.fullmatch(args.server_name):
        raise ValueError(
            "--server-name must be a lowercase Kubernetes DNS label of at most 63 characters"
        )
    java = args.java_version or select_java(args.minecraft_version)
    server_type = args.server_type.upper()
    if not re.fullmatch(r"[A-Z0-9_-]+", server_type):
        raise ValueError("--server-type must contain only letters, digits, underscore, or hyphen")

    memory_request = args.memory_request or f"{args.heap_gib}Gi"
    memory_limit = args.memory_limit or f"{args.heap_gib + 4}Gi"
    for option, value in (
        ("--cpu-request", args.cpu_request),
        ("--cpu-limit", args.cpu_limit),
        ("--memory-request", memory_request),
        ("--memory-limit", memory_limit),
    ):
        if not QUANTITY.fullmatch(value):
            raise ValueError(f"{option} has unsupported quantity {value!r}")
    request_gib = parse_gib(memory_request)
    limit_gib = parse_gib(memory_limit)
    if request_gib is not None and request_gib < args.heap_gib:
        raise ValueError("--memory-request must not be lower than --heap-gib")
    if limit_gib is not None and limit_gib <= args.heap_gib:
        raise ValueError("--memory-limit must be greater than --heap-gib")

    if args.storage_mode == "hostpath":
        missing = [
            option
            for option, value in (
                ("--node-name", args.node_name),
                ("--host-path", args.host_path),
                ("--gid", args.gid),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"hostpath mode requires {', '.join(missing)}")
        if not args.host_path.startswith("/"):
            raise ValueError("--host-path must be absolute")
        gid = args.gid
    else:
        if not args.pvc_capacity:
            raise ValueError("pvc mode requires --pvc-capacity")
        if not QUANTITY.fullmatch(args.pvc_capacity):
            raise ValueError("--pvc-capacity must be a positive Kubernetes quantity")
        gid = args.gid or "1000"

    return java, memory_request, memory_limit, parse_env(args.extra_env), parse_ports(args.extra_port)


def parse_gib(value: str) -> int | None:
    match = re.fullmatch(r"([1-9][0-9]*)Gi", value)
    return int(match.group(1)) if match else None


def env_block(
    args: argparse.Namespace,
    gid: str,
    extra_env: list[tuple[str, str]],
) -> list[str]:
    lines = [
        "          env:",
        "            # タイムゾーン",
        "            - name: TZ",
        '              value: "Asia/Tokyo"',
        "            # Minecraft EULAに同意する",
        "            - name: EULA",
        '              value: "true"',
        "            # サーバー実装",
        "            - name: TYPE",
        f"              value: {yaml_quote(args.server_type.upper())}",
        "            # itzg/minecraft-serverの最適化済みJVMフラグを使用する",
        "            - name: USE_AIKAR_FLAGS",
        '              value: "true"',
        "            # コンテナ内の実行UID/GID",
        "            - name: UID",
        '              value: "0"',
        "            - name: GID",
        f"              value: {yaml_quote(gid)}",
        "            # Minecraftバージョン",
        "            - name: VERSION",
        f"              value: {yaml_quote(args.minecraft_version)}",
        "            # JVMヒープ領域（-Xms / -Xmx）",
        "            - name: MEMORY",
        f'              value: "{args.heap_gib}G"',
        "            # 設定ファイル内でCFG_変数を展開する",
        "            - name: ENV_VARIABLE_PREFIX",
        '              value: "CFG_"',
    ]
    if args.jvm_opts:
        lines.extend(
            [
                "            # 追加JVMオプション",
                "            - name: JVM_OPTS",
                f"              value: {yaml_quote(args.jvm_opts)}",
            ]
        )
    if args.jvm_dd_opts:
        lines.extend(
            [
                "            # JVMの-Dオプション",
                "            - name: JVM_DD_OPTS",
                f"              value: {yaml_quote(args.jvm_dd_opts)}",
            ]
        )
    for name, value in extra_env:
        lines.extend(
            [
                "            # ユーザー指定の追加環境変数",
                f"            - name: {name}",
                f"              value: {yaml_quote(value)}",
            ]
        )
    lines.extend(
        [
            "            # Podメタデータをサーバー内から参照可能にする",
            "            - name: CFG_POD_NAME",
            "              valueFrom:",
            "                fieldRef:",
            "                  fieldPath: metadata.name",
            "            - name: CFG_POD_NAMESPACE",
            "              valueFrom:",
            "                fieldRef:",
            "                  fieldPath: metadata.namespace",
            "            - name: CFG_SERVER_NAME",
            "              valueFrom:",
            "                fieldRef:",
            "                  fieldPath: metadata.labels['kuvel.azisaba.net/preferred-server-name']",
            "            - name: POD_NAME",
            "              valueFrom:",
            "                fieldRef:",
            "                  fieldPath: metadata.name",
            "            - name: POD_NAMESPACE",
            "              valueFrom:",
            "                fieldRef:",
            "                  fieldPath: metadata.namespace",
            "            - name: SERVER_NAME",
            "              valueFrom:",
            "                fieldRef:",
            "                  fieldPath: metadata.labels['kuvel.azisaba.net/preferred-server-name']",
        ]
    )
    return lines


def generate(args: argparse.Namespace) -> str:
    java, memory_request, memory_limit, extra_env, extra_ports = validate(args)
    gid = args.gid if args.storage_mode == "hostpath" else (args.gid or "1000")
    name = args.server_name

    lines = [
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        f"  name: server-{name}",
        "spec:",
        "  selector:",
        "    matchLabels:",
        f"      app: server-{name}",
        "  # Minecraftのデータを同時に複数Podから書き換えない",
        "  strategy:",
        "    type: Recreate",
        "  revisionHistoryLimit: 2",
        "  template:",
        "    metadata:",
        "      labels:",
        f"        app: server-{name}",
        "        stage: production",
        '        kuvel.azisaba.net/enable-server-discovery: "true"',
        f"        kuvel.azisaba.net/preferred-server-name: {name}",
        '        kuvel.azisaba.net/disable-load-balancer: "true"',
        '        kuvel.azisaba.net/disable-name-suffix: "true"',
        "    spec:",
    ]
    if args.storage_mode == "hostpath":
        lines.extend(
            [
                "      # hostPathはノード固有のため、配置先を固定する",
                f"      nodeName: {args.node_name}",
            ]
        )
    lines.extend(
        [
            "      containers:",
            f"        - name: server-{name}",
            "          # Minecraftバージョンに対応するJavaイメージ",
            f"          image: itzg/minecraft-server:java{java}",
            "          workingDir: /data",
            "          imagePullPolicy: Always",
            "          resources:",
            "            requests:",
            f'              cpu: "{args.cpu_request}"',
            "              # スケジューリング時に確保するメモリ。既定はheapと同量",
            f'              memory: "{memory_request}"',
            "            limits:",
            f'              cpu: "{args.cpu_limit}"',
            "              # heapにoff-heapと余裕分を加え、OOMKillを避ける",
            f'              memory: "{memory_limit}"',
            "          ports:",
            "            - name: minecraft",
            "              containerPort: 25565",
        ]
    )
    for port in extra_ports:
        lines.extend(
            [
                f"            - name: {port.name}",
                f"              containerPort: {port.target_port}",
            ]
        )
    lines.extend(env_block(args, gid, extra_env))
    lines.extend(
        [
            "          # Minecraftの待受開始まで最大10分待機する",
            "          startupProbe:",
            "            tcpSocket:",
            "              port: 25565",
            "            failureThreshold: 60",
            "            periodSeconds: 10",
            "          volumeMounts:",
            "            - name: server-data",
            "              mountPath: /data",
        ]
    )
    if args.use_tab_config:
        lines.extend(
            [
                "            # アジ鯖共通のTAB設定",
                "            - name: tab-config",
                "              mountPath: /plugins/TAB/config.yml",
                "              subPath: config.yml",
            ]
        )
    lines.extend(["      volumes:", "        - name: server-data"])
    if args.storage_mode == "hostpath":
        lines.extend(
            [
                "          hostPath:",
                f"            path: {yaml_quote(args.host_path)}",
                "            type: Directory",
            ]
        )
    else:
        lines.extend(
            [
                "          persistentVolumeClaim:",
                f"            claimName: server-{name}-data-claim",
            ]
        )
    if args.use_tab_config:
        lines.extend(
            [
                "        - name: tab-config",
                "          configMap:",
                f"            name: {args.tab_config_name}",
            ]
        )
    lines.extend(
        [
            "      priorityClassName: minecraft-other-server",
            "      # stop処理とワールド保存のため1分待機する",
            "      terminationGracePeriodSeconds: 60",
        ]
    )

    if args.storage_mode == "pvc":
        lines.extend(
            [
                "---",
                "apiVersion: v1",
                "kind: PersistentVolumeClaim",
                "metadata:",
                f"  name: server-{name}-data-claim",
                "spec:",
                f"  storageClassName: {args.storage_class}",
                "  accessModes:",
                "    - ReadWriteMany",
                "  resources:",
                "    requests:",
                f"      storage: {yaml_quote(args.pvc_capacity)}",
            ]
        )

    lines.extend(
        [
            "---",
            "apiVersion: v1",
            "kind: Service",
            "metadata:",
            f"  name: server-{name}-svc",
            "spec:",
            "  type: ClusterIP",
            "  selector:",
            f"    app: server-{name}",
            "    stage: production",
            "  ports:",
            "    - name: minecraft",
            "      port: 25565",
            "      targetPort: 25565",
        ]
    )
    for port in extra_ports:
        lines.extend(
            [
                f"    - name: {port.name}",
                f"      port: {port.port}",
                f"      targetPort: {port.target_port}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parser().parse_args()
    try:
        sys.stdout.write(generate(args))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
