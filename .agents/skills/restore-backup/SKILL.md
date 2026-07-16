---
name: restore-backup
description: Restore files or directories from the Aji server restic backups. Use when Codex is asked to recover a path from the "アジ鯖" backups, interpret requests such as `saba12:/srv/life/nanntoka`, query remote restic snapshots over `ssh root@192.168.0.226`, narrow large snapshot output with `grep` or `tail`, choose the matching snapshot path under `/mnt/restic1/tmp/{host}/...`, stage the restore safely, and place the restored result onto the requested destination host and path via `scp`.
---

# Aji Restic Restore

## Overview

Recover a file or directory from the Aji server restic backups by mapping the requested live path to the backed-up path stored in the snapshot. Run `restic` only on the remote host through `ssh root@192.168.0.226`, stage the restore safely, then deliver the restored result to the user-specified destination via `scp`.

## Parse The Request

Extract these pieces from the user request:

- Host name, for example `saba12`
- Original live path, for example `/srv/life/nanntoka`
- Destination host and destination path, if the user provided them
- Optional snapshot id or restore date if the user provided one

If the user gives `host:path` syntax, split on the first `:` and treat the right-hand side as the live path.

If the user does not specify where the restored result should be placed, stop and ask for the destination path before doing the final transfer.

## Run Restic Remotely

Never run bare `restic ...` locally for this skill. Always execute it on the backup host through SSH.

Use this command shape:

```bash
ssh root@192.168.0.226 '<remote command here>'
```

This applies to:

- `restic snapshots`
- `restic restore`
- Any remote verification such as `ls`, `find`, or `stat` against staged restore paths

## Narrow Snapshot Output Before Choosing

`restic snapshots` can be very large. Filter on the remote side before inspecting results.

Start with the strongest stable path fragment you have, usually the host plus the nearest parent directory:

- Host fragment, for example `saba12`
- Parent directory fragment, for example `/srv/life`
- Optional deeper fragment when it is unlikely to overfilter

Prefer commands in this shape:

```bash
ssh root@192.168.0.226 "restic snapshots | grep '/mnt/restic1/tmp/saba12/srv/life' | tail -n 20"
```

If the exact path is not known yet, widen slightly:

```bash
ssh root@192.168.0.226 "restic snapshots | grep 'saba12' | grep '/srv/life' | tail -n 20"
```

Use `tail` to bias toward newer snapshots after filtering. If the user specified a date or snapshot id, filter for that as well before selecting a candidate.

Avoid dumping the full unfiltered `restic snapshots` output unless the user explicitly asks for it.

## Map The Live Path To The Snapshot Path

The backup layout mirrors the live tree beneath `/mnt/restic1/tmp/<host>`.

For a request like `saba12:/srv/life/nanntoka`:

- Snapshot root candidate: `/mnt/restic1/tmp/saba12/srv/life`
- Restored include path: `/mnt/restic1/tmp/saba12/srv/life/nanntoka`

Choose the snapshot whose stored path is the longest matching prefix of the requested live path after adding the `/mnt/restic1/tmp/<host>` prefix.

Example:

- Requested live path: `/srv/life/nanntoka`
- Snapshot line: `97ad1bca  2026-06-29 19:17:34  backup  /mnt/restic1/tmp/saba12/srv/life`
- Use snapshot id `97ad1bca`
- Restore include path `/mnt/restic1/tmp/saba12/srv/life/nanntoka`

If more than one snapshot matches:

- Prefer the snapshot id or date explicitly requested by the user.
- Otherwise prefer the newest matching snapshot.
- If there are multiple plausible roots with different meanings, pause and ask a narrow clarifying question.

## Restore Safely

Default to a staged restore on the backup host first.

1. Create a unique temporary target directory.
2. Restore only the requested subtree with `restic restore ... --include ...`.
3. Verify that the restored path exists in the staging directory.
4. Copy the restored result down to a local temporary directory.
5. Transfer it to the requested destination host and path.
6. Report the staging location, local temporary path, and final destination.

Use commands in this shape, adapting flags to the environment's existing restic setup:

```bash
ssh root@192.168.0.226 "restic restore <snapshot-id> --target <staging-dir> --include <snapshot-path>"
```

Worked example:

```bash
ssh root@192.168.0.226 "restic restore 97ad1bca --target /tmp/aji-restore-97ad1bca --include /mnt/restic1/tmp/saba12/srv/life/nanntoka"
```

After restore, expect the staged content under:

- `/tmp/aji-restore-97ad1bca/mnt/restic1/tmp/saba12/srv/life/nanntoka`

## Ask For The Final Destination

Do not guess the final placement path.

If the user only asks to restore a path from backup, ask a narrow follow-up such as:

- `どこに配置すればよいですか`
- `復元後、どのホストのどのパスへ置けばよいですか`

Proceed with the transfer only after the destination is explicit.

## Map Destination Hostnames

When the user gives a destination like `saba12:/home/perfectboat`, derive the transfer target like this:

- Strip the `saba` prefix and keep the numeric suffix, here `12`
- Build the destination host IP as `192.168.100.1<suffix>`, here `192.168.100.112`
- Use the path part as the remote destination path, here `/home/perfectboat`
- Use the last path segment as the SSH user when the user does not specify another account, here `perfectboat`

For `saba12:/home/perfectboat`, the final transfer target becomes:

- User: `perfectboat`
- Host: `192.168.100.112`
- Path: `/home/perfectboat/`

If the hostname does not match the `saba<number>` pattern, or if the login user cannot be inferred safely from the destination path, stop and ask a narrow clarifying question.

## Copy Down Locally Before Final Transfer

Do not copy directly from the backup host into the final destination host.

Always:

1. Restore on `192.168.0.226`
2. Pull the restored result into a local temporary directory with `scp`
3. Push from local temp into the final destination host with `scp`

For a single file, use a command shape like:

```bash
scp root@192.168.0.226:/tmp/aji-restore-97ad1bca/mnt/restic1/tmp/saba12/path/to/file ./work/tmp/file
scp ./work/tmp/file perfectboat@192.168.100.112:/home/perfectboat/
```

Choose a unique local temp directory and verify the downloaded file exists before the second `scp`.

## Handle Directories Without Rsync

Assume `rsync` is not available in this environment.

If the requested restore result is a directory:

1. Create a zip archive from the restored directory
2. Copy the zip file down locally with `scp`
3. Transfer the zip file to the final destination host with `scp`
4. Report clearly that a zip archive was delivered, including its filename

Example command shape on the backup host:

```bash
ssh root@192.168.0.226 "cd /tmp/aji-restore-97ad1bca/mnt/restic1/tmp/saba12/srv/life && zip -r /tmp/nanntoka-97ad1bca.zip nanntoka"
scp root@192.168.0.226:/tmp/nanntoka-97ad1bca.zip ./work/tmp/nanntoka-97ad1bca.zip
scp ./work/tmp/nanntoka-97ad1bca.zip perfectboat@192.168.100.112:/home/perfectboat/
```

Do not silently switch to tar or another archive format unless the user asks for it.

## Verify Before Declaring Success

Always verify the actual restored path, not just the command exit code.

Check:

- The restored directory or file exists
- The local temporary copy or zip exists before the final upload
- The expected file count or representative filenames are present when practical
- The snapshot id used is included in the final report
- The final `scp` destination matches the requested host and path

Useful remote verification shapes:

```bash
ssh root@192.168.0.226 "ls -la /tmp/aji-restore-97ad1bca/mnt/restic1/tmp/saba12/srv/life/nanntoka"
ssh root@192.168.0.226 "find /tmp/aji-restore-97ad1bca/mnt/restic1/tmp/saba12/srv/life/nanntoka -maxdepth 2 | head -n 20"
```

If verification fails, report exactly which path was missing and stop before the next transfer step.

## Keep Questions Narrow

Do not ask broad setup questions if the environment already shows the needed snapshot list or restic configuration.

Only stop to ask when one of these is missing:

- The host name cannot be determined
- No matching snapshot path can be identified
- The final destination path or transfer account is not specified or cannot be inferred safely
- The user specified a historical point in time but no matching snapshot is visible

## Final Response Shape

When the restore succeeds, report:

- The original requested path
- The snapshot id and timestamp used
- The exact snapshot path included in the restore
- The staging directory on `192.168.0.226`
- The local temporary path used for relay
- The final uploaded host, user, and destination path
- Whether the delivered artifact was a file or a zip archive

When making a reasonable assumption, state it briefly after the work is complete.
