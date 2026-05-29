"""Record and display output signals.

Used in the Logic Simulator project to record and display specified output
signals.

Classes
-------
Monitors - records and displays specified output signals.

"""
import collections

# Changes made by Kevin: 
# 1. 
#     Due to separation of network.DEVICE_ABSENT into 
#     FIRST_DEVICE_ABSENT and SECOND_DEVICE_ABSENT
#     in network.py, we remove usage of network.DEVICE_ABSENT
#     and replace with a separate DEVICE_ABSENT in the Monitors class.
# 2.  
#     Restructure how a Monitor is stored with a new object - 
#     this is to allow the proper display name for a monitored
#     net, allow monitoring a net and its driving device
#     together without monitor already exists error, etc.

class Monitor:

    """An object representing a Monitor.
     
      This class contains a requested_name field to keep track of whether the monitor was
      targetting the output device directly or a net driven by the output device. 
      """
    def __init__(self, requested_name, device_id, output_id, blank_signal,
                 cycles_completed=0):

        self.requested_name = requested_name
        self.device_id = device_id
        self.output_id = output_id
        self.trace = [blank_signal] * cycles_completed
 

class Monitors:

    """Record and display output signals.

    This class contains functions for recording and displaying the signal state
    of outputs specified by their device and port IDs.

    Parameters
    ----------
    names: instance of the names.Names() class.
    devices: instance of the devices.Devices() class.
    network: instance of the network.Network() class.

    Public methods
    --------------
    make_monitor(self, device_id, output_id): Sets a specified monitor on the
                                              specified output.

    remove_monitor(self, device_id, output_id): Removes a monitor from the
                                                specified output.

    get_monitor_signal(self, device_id, output_id): Returns the signal level of
                                                    the specified monitor.

    record_signals(self): Records the current signal level of all monitors.

    get_signal_names(self): Returns two lists of signal names: monitored and
                            not monitored.

    reset_monitors(self): Clears the memory of all monitors.

    get_margin(self): Returns the length of the longest monitor's name.

    display_signals(self): Displays signal trace(s) in the text console.
    """

    def __init__(self, names, devices, network):
        """Initialise the monitors dictionary and monitor errors."""
        self.names = names
        self.network = network
        self.devices = devices

        # monitors_dictionary maps requested_name -> Monitor object.
        # The requested name is what the user wrote or selected, possibly a net
        # name. The Monitor stores the resolved real device/output to sample.
        self.monitors_dictionary = collections.OrderedDict()

        [self.NO_ERROR, self.NOT_OUTPUT,
         self.MONITOR_PRESENT, self.DEVICE_ABSENT] = self.names.unique_error_codes(4)
    
    def make_monitor(self, device_id, output_id, requested_name, cycles_completed=0):
        """Add the specified signal to the monitors dictionary.

        Return NO_ERROR if successful, or the corresponding error if not.
        """
        monitor_device = self.devices.get_device(device_id)
        if monitor_device is None:
            return self.DEVICE_ABSENT
        elif output_id not in monitor_device.outputs:
            return self.NOT_OUTPUT
        if requested_name in self.monitors_dictionary:
            return self.MONITOR_PRESENT
        else:
            # If n simulation cycles have been completed before making this
            # monitor, then initialise the signal trace with an n-length list
            # of BLANK signals. Otherwise, initialise the trace with an empty
            # list.
            self.monitors_dictionary[requested_name] = Monitor(
            requested_name,
            device_id,
            output_id,
            self.devices.BLANK,
            cycles_completed,
        )
        return self.NO_ERROR

    def remove_monitor(self, requested_name):
        """Remove the specified monitor.

        Return True if successful.
        """
        if requested_name not in self.monitors_dictionary:
            return False

        del self.monitors_dictionary[requested_name]
        return True

    def get_monitor_signal(self, requested_name):
        """Return the signal level of the specified monitor.

        If the monitor does not exist, return None.
        """
        monitor = self.monitors_dictionary.get(requested_name)
        if monitor is None:
            return None

        return self.network.get_output_signal(
            monitor.device_id,
            monitor.output_id,
        )
    

    def record_signals(self):
        """Record the current signal level for every monitor.

        This function is called at every simulation cycle.
        """
        for monitor in self.monitors_dictionary.values():
            signal_level = self.network.get_output_signal(
                monitor.device_id,
                monitor.output_id,
            )
            monitor.trace.append(signal_level)

    def get_signal_names(self):
        """Return two signal name lists: monitored and not monitored."""
        non_monitored_signal_list = []
        monitored_signal_list = list(self.monitors_dictionary.keys())
        monitored_sources = {
            (monitor.device_id, monitor.output_id)
            for monitor in self.monitors_dictionary.values()
        }

        for device_id in self.devices.find_devices():
            device = self.devices.get_device(device_id)
            for output_id in device.outputs:
                if (device_id, output_id) not in monitored_sources:
                    signal_name = self.devices.get_signal_name(device_id,
                                                               output_id)
                    non_monitored_signal_list.append(signal_name)

        return [monitored_signal_list, non_monitored_signal_list]

    def reset_monitors(self):
        """Clear the memory of all the monitors.

        The list of stored signal levels for each monitor is deleted.
        """
        for monitor in self.monitors_dictionary.values():
            monitor.trace = []

    def get_margin(self):
        """Return the length of the longest monitor's name.

        Return None if no signals are being monitored. This is useful for
        finding out how much space to leave after each monitor's name before
        starting to draw the signal trace.
        """
        if not self.monitors_dictionary:
            return None

        return max(
            len(monitor.requested_name)
            for monitor in self.monitors_dictionary.values()
        )

    def display_signals(self):
        """Display the signal trace(s) in the text console."""
        margin = self.get_margin()
        for monitor in self.monitors_dictionary.values():
            monitor_name = monitor.requested_name
            name_length = len(monitor_name)
            signal_list = monitor.trace
            print(monitor_name + (margin - name_length) * " ", end=": ")
            for signal in signal_list:
                if signal == self.devices.HIGH:
                    print("-", end="")
                if signal == self.devices.LOW:
                    print("_", end="")
                if signal == self.devices.RISING:
                    print("/", end="")
                if signal == self.devices.FALLING:
                    print("\\", end="")
                if signal == self.devices.BLANK:
                    print(" ", end="")
            print("\n", end="")
