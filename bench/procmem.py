"""Per-process memory on macOS from proc_pid_rusage: the footprint Activity Monitor shows and its lifetime peak."""
import ctypes
import subprocess

_libproc = ctypes.CDLL('/usr/lib/libproc.dylib')
_RUSAGE_INFO_V4 = 4


class _RusageInfoV4(ctypes.Structure):
    _fields_ = [('ri_uuid', ctypes.c_uint8 * 16)] + [(name, ctypes.c_uint64) for name in (
        'ri_user_time', 'ri_system_time', 'ri_pkg_idle_wkups', 'ri_interrupt_wkups', 'ri_pageins',
        'ri_wired_size', 'ri_resident_size', 'ri_phys_footprint', 'ri_proc_start_abstime',
        'ri_proc_exit_abstime', 'ri_child_user_time', 'ri_child_system_time', 'ri_child_pkg_idle_wkups',
        'ri_child_interrupt_wkups', 'ri_child_pageins', 'ri_child_elapsed_abstime', 'ri_diskio_bytesread',
        'ri_diskio_byteswritten', 'ri_cpu_time_qos_default', 'ri_cpu_time_qos_maintenance',
        'ri_cpu_time_qos_background', 'ri_cpu_time_qos_utility', 'ri_cpu_time_qos_legacy',
        'ri_cpu_time_qos_user_initiated', 'ri_cpu_time_qos_user_interactive', 'ri_billed_system_time',
        'ri_serviced_system_time', 'ri_logical_writes', 'ri_lifetime_max_phys_footprint', 'ri_instructions',
        'ri_cycles', 'ri_billed_energy', 'ri_serviced_energy', 'ri_interval_max_phys_footprint',
        'ri_runnable_time')]


def usage(pid):
    """Returns (footprint, lifetime peak footprint, resident size) in bytes, or None if the process is gone."""
    info = _RusageInfoV4()
    if 0 != _libproc.proc_pid_rusage(pid, _RUSAGE_INFO_V4, ctypes.byref(info)):
        return None
    return info.ri_phys_footprint, info.ri_lifetime_max_phys_footprint, info.ri_resident_size


def processes():
    """Maps pid to (ppid, command line) for every process of this user."""
    out = subprocess.run(['ps', '-xo', 'pid=,ppid=,args='], capture_output=True, text=True, check=True).stdout
    table = {}
    for line in out.splitlines():
        pid, ppid, args = line.strip().split(None, 2)
        table[int(pid)] = (int(ppid), args)
    return table


_responsible = ctypes.CDLL(None).responsibility_get_pid_responsible_for_pid
_responsible.restype = ctypes.c_int
_responsible.argtypes = [ctypes.c_int]


def responsible(pid):
    """The pid macOS charges this process to: an app for its WebKit services, as Activity Monitor groups them."""
    return _responsible(pid)
