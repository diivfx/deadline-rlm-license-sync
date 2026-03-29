import re
import socket

from System.Diagnostics import ProcessStartInfo, Process

from Deadline.Events import DeadlineEventListener
from Deadline.Scripting import ClientUtils, RepositoryUtils


def GetDeadlineEventListener():
    return RLMLicenseSync()


def CleanupDeadlineEventListener(deadlinePlugin):
    deadlinePlugin.Cleanup()


class RLMLicenseSync(DeadlineEventListener):
    def __init__(self):
        super(RLMLicenseSync, self).__init__()
        self.OnHouseCleaningCallback += self.OnHouseCleaning

    def Cleanup(self):
        del self.OnHouseCleaningCallback

    def OnHouseCleaning(self):
        # Only run on the Repository server (skip if RepositoryHost is configured)
        allowed_host = self.GetConfigEntryWithDefault("RepositoryHost", "")
        if allowed_host:
            current_host = socket.gethostname()
            if current_host.lower() != allowed_host.lower():
                return

        self.LogInfo("RLMLicenseSync: Starting license sync cycle.")

        # Read config
        rlm_server = self.GetConfigEntryWithDefault("RLMServer", "localhost")
        rlm_port = self.GetConfigEntryWithDefault("RLMPort", "4101")
        rlmutil_path = self.GetConfigEntryWithDefault("RLMUtilPath", "rlmutil")
        license_product = self.GetConfigEntryWithDefault("LicenseProduct", "nuke_i")
        limit_group_name = self.GetConfigEntryWithDefault("LimitGroupName", "nuke")
        timeout = int(self.GetConfigEntryWithDefault("Timeout", "10"))

        # Query RLM
        rlmstat_output = self._query_rlm(rlmutil_path, rlm_server, rlm_port, timeout)
        if rlmstat_output is None:
            return

        # Parse output
        license_info = self._parse_rlmstat(rlmstat_output, license_product)
        if license_info is None:
            return

        total, in_use, checkout_hosts = license_info

        # Update limit group
        self._update_limit_group(limit_group_name, total, in_use, checkout_hosts)

        self.LogInfo("RLMLicenseSync: Cycle complete.")

    def _query_rlm(self, rlmutil_path, server, port, timeout):
        """Shell out to rlmutil rlmstat and return stdout, or None on failure."""
        args = "rlmstat -c {0}@{1} -a".format(port, server)
        self.LogInfo("RLMLicenseSync: Running: {0} {1}".format(rlmutil_path, args))

        try:
            start_info = ProcessStartInfo()
            start_info.FileName = rlmutil_path
            start_info.Arguments = args
            start_info.UseShellExecute = False
            start_info.RedirectStandardOutput = True
            start_info.RedirectStandardError = True
            start_info.CreateNoWindow = True

            process = Process()
            process.StartInfo = start_info
            process.Start()

            # Read stdout before WaitForExit to avoid pipe buffer deadlock
            stdout = process.StandardOutput.ReadToEnd()
            stderr = process.StandardError.ReadToEnd()

            finished = process.WaitForExit(timeout * 1000)
            if not finished:
                self.LogWarning("RLMLicenseSync: rlmutil timed out after {0}s. Skipping cycle.".format(timeout))
                try:
                    process.Kill()
                except Exception:
                    pass
                finally:
                    process.Close()
                return None

            if process.ExitCode != 0:
                self.LogWarning("RLMLicenseSync: rlmutil exited with code {0}. stderr: {1}".format(
                    process.ExitCode, stderr.strip()))
                return None

            return stdout

        except Exception as e:
            self.LogWarning("RLMLicenseSync: Failed to run rlmutil: {0}".format(str(e)))
            return None

    def _parse_rlmstat(self, output, product):
        """Parse rlmstat output. Returns (total, in_use, [hostnames]) or None on failure.

        Parses two sections of rlmstat -a output:
        1. "license pool status" — for total count and inuse count per version
        2. "license usage status" — for checkout hostnames (user@hostname format)

        Example pool format:
            nuke_i v2027.0212
                    count: 1, # reservations: 0, inuse: 1, exp: 15-feb-2027
                    obsolete: 0, min_remove: 120, total checkouts: 809

        Example usage format:
            nuke_i v2027.0212: artist@workstation-07 1/0 at 03/29 13:02  (handle: 41)
        """
        lines = output.replace("\r\n", "\n").split("\n")

        total = 0
        in_use = 0
        checkout_hosts = []
        found_any = False

        # Pattern for usage lines: "nuke_i v2027.0212: user@hostname 1/0 at ..."
        usage_pattern = re.compile(
            r"^\s*" + re.escape(product) + r"\s+v\S+:\s+\S+@(\S+)\s+"
        )

        for line in lines:
            stripped = line.strip()

            # Parse pool section: count/inuse lines follow product headers
            count_match = re.search(r"count:\s*(\d+)", stripped)
            inuse_match = re.search(r"inuse:\s*(\d+)", stripped)
            if count_match and inuse_match:
                total += int(count_match.group(1))
                in_use += int(inuse_match.group(1))
                found_any = True
                continue

            # Parse usage section: "nuke_i v2027.0212: user@hostname ..."
            usage_match = usage_pattern.match(line)
            if usage_match:
                hostname = usage_match.group(1)
                if hostname not in checkout_hosts:
                    checkout_hosts.append(hostname)
                found_any = True

        if not found_any:
            self.LogWarning("RLMLicenseSync: Failed to parse rlmstat output. Could not find '{0}'.".format(product))
            self.LogInfo("RLMLicenseSync: Raw output:\n{0}".format(output))
            return None

        self.LogInfo("RLMLicenseSync: Parsed: total={0}, in_use={1}, checkouts={2}".format(
            total, in_use, checkout_hosts))

        return (total, in_use, checkout_hosts)

    def _update_limit_group(self, limit_group_name, total, in_use, checkout_hosts):
        """Update the Deadline limit group maximum and exclusion list."""
        free = total - in_use

        # Get or create the limit group
        limit_group = RepositoryUtils.GetLimitGroup(limit_group_name, True)
        if limit_group is None:
            self.LogWarning("RLMLicenseSync: Limit group '{0}' not found. Please create it manually in Deadline Monitor.".format(limit_group_name))
            return

        # Build exclusion list: match checkout hostnames to Deadline worker names
        worker_names = self._get_all_worker_names()
        worker_lookup = {name.lower(): name for name in worker_names}

        excluded_workers = []
        for host in checkout_hosts:
            worker_name = worker_lookup.get(host.lower())
            if worker_name:
                excluded_workers.append(worker_name)
            else:
                self.LogInfo("RLMLicenseSync: Checkout host '{0}' is not a Deadline worker. Ignoring for exclusion.".format(host))

        excluded_workers = list(set(excluded_workers))

        # Update the limit group
        try:
            RepositoryUtils.SetLimitGroupMaximum(limit_group_name, free)
            limit_group.SetLimitGroupExcludedSlaves(excluded_workers)
            RepositoryUtils.SaveLimitGroup(limit_group)
            self.LogInfo("RLMLicenseSync: Updated '{0}': limit={1}, excluded={2}".format(
                limit_group_name, free, excluded_workers))
        except Exception as e:
            self.LogWarning("RLMLicenseSync: Failed to update limit group: {0}".format(str(e)))

    def _get_all_worker_names(self):
        """Return a list of all Deadline worker names."""
        try:
            worker_infos = RepositoryUtils.GetSlaveInfos(True)
            return [info.SlaveName for info in worker_infos]
        except Exception as e:
            self.LogWarning("RLMLicenseSync: Failed to get worker list: {0}".format(str(e)))
            return []
