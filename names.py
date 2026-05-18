"""Map variable names and string names to unique integers.

Used in the Logic Simulator project. Most of the modules in the project
use this module either directly or indirectly.

Classes
-------
Names - maps variable names and string names to unique integers.
"""


class Names:

    """Map variable names and string names to unique integers.

    This class deals with storing grammatical keywords and user-defined words,
    and their corresponding name IDs, which are internal indexing integers. It
    provides functions for looking up either the name ID or the name string.
    It also keeps track of the number of error codes defined by other classes,
    and allocates new, unique error codes on demand.

    Parameters
    ----------
    No parameters.

    Public methods
    -------------
    unique_error_codes(self, num_error_codes): Returns a list of unique integer
                                               error codes.

    query(self, name_string): Returns the corresponding name ID for the
                        name string. Returns None if the string is not present.

    lookup(self, name_string_list): Returns a list of name IDs for each
                        name string. Adds a name if not already present.

    get_name_string(self, name_id): Returns the corresponding name string for
                        the name ID. Returns None if the ID is not present.
    """

    def __init__(self):
        """Initialises names list, dictionary, and error count."""
        self.error_code_count = 0 
        self.names = []            
        self._name_to_id = {}      

    def unique_error_codes(self, num_error_codes):
        """Returns a sequence of unique integer error codes."""
        # Strict type check cleanly rejects booleans and floats
        if type(num_error_codes) is not int or num_error_codes <= 0:
            raise ValueError("Expected num_error_codes to be a positive integer.")        
        
        start = self.error_code_count
        self.error_code_count += num_error_codes
        return range(start, self.error_code_count)

    def query(self, name_string):
        """Returns the corresponding name ID for name_string, or None if missing."""
        if type(name_string) is not str:
            raise TypeError("Expected name_string to be a string.") 
        return self._name_to_id.get(name_string)

    def lookup(self, name_strings):
        """Returns a list of name IDs for each string. Adds name if missing."""
        if type(name_strings) in (str, bytes) or not hasattr(name_strings, '__iter__'):
            raise TypeError("Expected an iterable collection of strings (e.g., a list).")
            
        ids = []
    
        name_map = self._name_to_id
        append_name = self.names.append
        append_id = ids.append
        names_len = len(self.names)
        
        for name in name_strings:
            if type(name) is not str:
                raise TypeError(f"Iterable must contain only strings, found: {type(name).__name__}.")
            
            if name not in name_map:
                name_map[name] = names_len
                append_name(name)
                names_len += 1
                
            append_id(name_map[name])
            
        return ids

    def get_name_string(self, name_id):
        """Returns the corresponding name string for name_id, or None if invalid."""
        if type(name_id) is not int:
            raise TypeError("Expected name_id to be an integer.")
    
        if 0 <= name_id < len(self.names):
            return self.names[name_id]
        return None
