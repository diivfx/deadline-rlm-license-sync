# Deadline RLM License Sync

A Deadline Event Plugin that syncs [RLM](https://www.reprisesoftware.com/products/software-license-management.php) floating license availability into Deadline limit groups, preventing license-fail errors on the render farm.

## How It Works

On each Deadline HouseCleaning cycle (~60 seconds), the plugin:

1. Queries the RLM license server via `rlmutil rlmstat -a`
2. Parses total license count, in-use count, and which machines have licenses checked out
3. Updates a Deadline limit group:
   - **Limit = free licenses** (total - in use)
   - **Workers Excluded From Limit = workers that already hold a license** (they bypass the limit entirely and can always pick up jobs)

### Why Exclusions?

If an artist has an application open on their workstation (which is also a Deadline worker), that machine already has a license checked out. By adding it to the limit group's "Workers Excluded From Limit" list, the worker bypasses the limit entirely and can always pick up jobs -- the license is already in use on that machine anyway.

**Important:** This uses Deadline's "Excluded From Limit" list, which is different from the allow/deny list. The allow/deny list controls which workers *can* use the limit group. The excluded list lets workers bypass the limit count entirely.

### Supported Products

While the examples below use Nuke, this plugin works with **any RLM-managed license product**. The `LicenseProduct` field supports comma-separated values -- all products are summed into a single limit group.

**Single product:**
- `LicenseProduct=nuke_i` -- track interactive licenses only

**Multiple products in one limit group:**
- `LicenseProduct=nuke_i,nuke_r` -- track both interactive and render licenses together

**Separate limit groups for different applications:**

Deploy multiple instances of the plugin (copy the directory with a different name) to manage independent limit groups. For example:

| Plugin Directory | LicenseProduct | LimitGroupName |
|---|---|---|
| `RLMLicenseSync/` | `nuke_i,nuke_r` | `nuke` |
| `RLMLicenseSync_Mari/` | `mari_i` | `mari` |

## Installation

1. Copy `RLMLicenseSync.py` and `RLMLicenseSync.param` to your Deadline Repository:
   ```
   <DeadlineRepository>/custom/events/RLMLicenseSync/
   ```

2. Ensure `rlmutil` is available on the machine(s) that will run the plugin (see [Deployment Considerations](#deployment-considerations) below).

3. Create the limit group in Deadline Monitor:
   **Tools > Manage Limit Groups > Add**

4. Enable the plugin:
   **Tools > Configure Event Plugins > RLMLicenseSync > State: Global Enabled**

5. Configure your settings (RLM server IP, port, rlmutil path, etc.)

6. Add the limit group to your job submissions (e.g. `LimitGroups=nuke`)

## Configuration

| Parameter | Default | Description |
|---|---|---|
| State | Global Disabled | Enable/disable the plugin |
| RepositoryHost | *(your hostname)* | Hostname of the Repository machine. Plugin only runs here. |
| RLMServer | *(your RLM server IP)* | RLM license server hostname/IP |
| RLMPort | 4101 | RLM server port |
| RLMUtilPath | rlmutil | Path to `rlmutil` binary |
| LicenseProduct | nuke_i | Comma-separated RLM product names (e.g. `nuke_i,nuke_r`) |
| LimitGroupName | nuke | Deadline limit group to manage |
| Timeout | 10 | Seconds to wait for `rlmutil` response |

> **Note:** After installation, update `RepositoryHost` and `RLMServer` in the plugin configuration to match your environment.

## Deployment Considerations

### Where the plugin runs

Deadline event plugins triggered by `OnHouseCleaning` run on whichever application performs house cleaning -- this can be Pulse, a Worker, or even Deadline Monitor. By default, any of these may trigger the plugin.

**Recommended: Run only on the Repository server via Pulse**

The simplest setup is to run the plugin exclusively on the machine hosting Deadline Pulse (typically your Repository server). To do this:

1. Set `RepositoryHost` in the plugin config to your Repository server's hostname. The plugin will silently skip execution on all other machines.
2. In Deadline Monitor, go to **Tools > Configure Repository Options > House Cleaning** and disable **"Allow Workers to Perform House Cleaning If Pulse is Not Running"**. This ensures only Pulse performs house cleaning.
3. Add `rlmutil` to the system `PATH` on the Repository server (e.g. via symlink to `/usr/local/bin/`), or set `RLMUtilPath` to the full path.

### Alternative: Allow any client to run it

If you prefer the plugin to run from any Deadline client (Worker, Monitor, etc.), remove the `RepositoryHost` guard or set it to match multiple machines. In this case, `rlmutil` must be accessible from every machine that might trigger house cleaning. Options:

- **Shared network path** -- place `rlmutil` on a network share and set `RLMUtilPath` to the UNC/mount path (e.g. `\\server\share\rlmutil.exe` or `/mnt/share/rlmutil`)
- **Install locally** -- install `rlmutil` on every Worker/client machine and add it to `PATH`

Note that in this mode, multiple machines may run the plugin concurrently during the same house cleaning cycle. This is harmless (they'll all compute the same result), but generates redundant log entries.

## RLM Output Format

The plugin parses two sections from `rlmutil rlmstat -a`:

**License pool** (counts):
```
nuke_i v2027.0212
        count: 1, # reservations: 0, inuse: 1, exp: 15-feb-2027
        obsolete: 0, min_remove: 120, total checkouts: 809
```

**License usage** (who has what):
```
nuke_i v2027.0212: artist@workstation-07 1/0 at 03/29 13:02  (handle: 41)
```

Multiple version blocks for the same product are summed automatically.

## Error Handling

- If `rlmutil` fails, times out, or returns unexpected output, the plugin logs a warning and skips the cycle -- the limit group is never degraded on a transient error.
- If the limit group doesn't exist, the plugin logs a warning asking you to create it manually.
- The plugin silently skips execution on any machine that isn't the configured `RepositoryHost`.

## Requirements

- Deadline 10+
- `rlmutil` (from [Reprise Software](https://www.reprisesoftware.com/) or bundled with Foundry Licensing Tools)
- Network access from the Repository machine to the RLM server

## License

MIT
