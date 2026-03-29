# Deadline RLM License Sync

A Deadline Event Plugin that syncs [RLM](https://www.reprisesoftware.com/products/software-license-management.php) floating license availability into Deadline limit groups, preventing license-fail errors on the render farm.

## How It Works

On each Deadline HouseCleaning cycle (~60 seconds), the plugin:

1. Queries the RLM license server via `rlmutil rlmstat -a`
2. Parses total license count, in-use count, and which machines have licenses checked out
3. Updates a Deadline limit group:
   - **Limit = free licenses** (total - in use)
   - **Exclusion list = workers that already hold a license** (they bypass the limit)

### Why Exclusions?

If an artist has Nuke open on their workstation (which is also a Deadline worker), that machine already has a license checked out. By excluding it from the limit group, the worker can still pick up Nuke jobs without consuming a limit slot -- the license is already in use on that machine anyway.

## Installation

1. Copy `RLMLicenseSync.py` and `RLMLicenseSync.param` to your Deadline Repository:
   ```
   <DeadlineRepository>/custom/events/RLMLicenseSync/
   ```

2. Ensure `rlmutil` is available on the machine running the Deadline Repository/Pulse service (either on `PATH` or specify the full path in the plugin config).

3. Create the limit group in Deadline Monitor:
   **Tools > Manage Limit Groups > Add** (default name: `nuke`)

4. Enable the plugin:
   **Tools > Configure Event Plugins > RLMLicenseSync > State: Global Enabled**

5. Configure your settings (RLM server IP, port, rlmutil path, etc.)

6. Add the limit group to your Nuke job submissions (`LimitGroups=nuke`)

## Configuration

| Parameter | Default | Description |
|---|---|---|
| State | Global Disabled | Enable/disable the plugin |
| RepositoryHost | RedividerServer | Hostname of the Repository machine. Plugin only runs here. |
| RLMServer | 192.168.2.40 | RLM license server hostname/IP |
| RLMPort | 4101 | RLM server port |
| RLMUtilPath | rlmutil | Path to `rlmutil` binary |
| LicenseProduct | nuke_i | RLM product name to track (e.g. `nuke_i`, `nuke_r`, `nukex_i`) |
| LimitGroupName | nuke | Deadline limit group to manage |
| Timeout | 10 | Seconds to wait for `rlmutil` response |

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
nuke_i v2027.0212: dieuwer@workstation-07 1/0 at 03/29 13:02  (handle: 41)
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
