"""Record and display output signals.

Used in the Logic Simulator project to record and display specified output
signals.

Classes
-------
Monitors - records and displays specified output signals.

"""
import collections

# Slight changes made by Kevin: 
# 1. 
#     Due to separation of network.DEVICE_ABSENT into 
#     FIRST_DEVICE_ABSENT and SECOND_DEVICE_ABSENT
#     in network.py, we remove usage of network.DEVICE_ABSENT
#     and replace with a separate DEVICE_ABSENT in the Monitors class.
# 2.  
#     Add functionality for the display_name for a monitor
#     to be different to the actual driving source name.
#     This is useful to display the net name instead of the
#     device name when the user creates a monitor on a net. 
 

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

        # monitors_dictionary stores
        # {(device_id, output_id): [signal_list]}
        self.monitors_dictionary = collections.OrderedDict()

        # Some monitors are referred to by the net name, e.g. partial_sum
        # and resolved to the driver name, like XOR.
        # This dictionary allows storage of the net name / user-facing name
        # that should be displayed in the GUI.
        self.monitor_display_names = {}

        [self.NO_ERROR, self.NOT_OUTPUT,
         self.MONITOR_PRESENT, self.DEVICE_ABSENT] = self.names.unique_error_codes(4)

    def make_monitor(self, device_id, output_id, cycles_completed=0):
        """Add the specified signal to the monitors dictionary.

        Return NO_ERROR if successful, or the corresponding error if not.
        """
        monitor_device = self.devices.get_device(device_id)
        if monitor_device is None:
            return self.DEVICE_ABSENT
        elif output_id not in monitor_device.outputs:
            return self.NOT_OUTPUT
        elif (device_id, output_id) in self.monitors_dictionary:
            return self.MONITOR_PRESENT
        else:
            # If n simulation cycles have been completed before making this
            # monitor, then initialise the signal trace with an n-length list
            # of BLANK signals. Otherwise, initialise the trace with an empty
            # list.
            self.monitors_dictionary[(device_id, output_id)] = [
                self.devices.BLANK] * cycles_completed
            return self.NO_ERROR

    def remove_monitor(self, device_id, output_id):
        """Remove the specified signal from the monitors dictionary.

        Return True if successful.
        """
        if (device_id, output_id) not in self.monitors_dictionary:
            return False
        else:
            del self.monitors_dictionary[(device_id, output_id)]
            return True

    def get_monitor_signal(self, device_id, output_id):
        """Return the signal level of the specified monitor.

        If the monitor does not exist, return None.
        """
        if (device_id, output_id) in self.monitors_dictionary:
            return self.network.get_output_signal(device_id, output_id)
        else:
            return None
    
    # Added to support displaying net name rather than device name
    def set_monitor_display_name(self, device_id, output_id, display_name):
        """Store the name that should be displayed for a monitored signal."""
        self.monitor_display_names[(device_id, output_id)] = display_name

    def get_monitor_display_name(self, device_id, output_id):
        """Return the display name for a monitored signal."""
        signal_key = (device_id, output_id)

        if signal_key in self.monitor_display_names:
            return self.monitor_display_names[signal_key]

        return self.devices.get_signal_name(device_id, output_id)

    def record_signals(self):
        """Record the current signal level for every monitor.

        This function is called at every simulation cycle.
        """
        for device_id, output_id in self.monitors_dictionary:
            signal_level = self.get_monitor_signal(device_id, output_id)
            self.monitors_dictionary[(device_id,
                                      output_id)].append(signal_level)

    def get_signal_names(self):
        """Return two signal name lists: monitored and not monitored."""
        non_monitored_signal_list = []
        monitored_signal_list = []
        for device_id, output_id in self.monitors_dictionary:
            monitor_name = self.get_monitor_display_name(device_id, output_id)
            monitored_signal_list.append(monitor_name)

        for device_id in self.devices.find_devices():
            device = self.devices.get_device(device_id)
            for output_id in device.outputs:
                if (device_id, output_id) not in self.monitors_dictionary:
                    signal_name = self.devices.get_signal_name(device_id,
                                                               output_id)
                    non_monitored_signal_list.append(signal_name)

        return [monitored_signal_list, non_monitored_signal_list]

    def reset_monitors(self):
        """Clear the memory of all the monitors.

        The list of stored signal levels for each monitor is deleted.
        """
        for device_id, output_id in self.monitors_dictionary:
            self.monitors_dictionary[(device_id, output_id)] = []

    def get_margin(self):
        """Return the length of the longest monitor's name.

        Return None if no signals are being monitored. This is useful for
        finding out how much space to leave after each monitor's name before
        starting to draw the signal trace.
        """
        length_list = []  # for storing name lengths
        for device_id, output_id in self.monitors_dictionary:
            monitor_name = self.get_monitor_display_name(device_id, output_id)
            name_length = len(monitor_name)
            length_list.append(name_length)
        if length_list:  # if the list is not empty
            return max(length_list)
        else:
            return None

    def display_signals(self):
        """Display the signal trace(s) in the text console."""
        margin = self.get_margin()
        for device_id, output_id in self.monitors_dictionary:
            monitor_name = self.get_monitor_display_name(device_id, output_id)
            name_length = len(monitor_name)
            signal_list = self.monitors_dictionary[(device_id, output_id)]
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
