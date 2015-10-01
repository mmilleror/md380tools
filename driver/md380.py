# Copyright 2012 Dan Smith <dsmith@danplanet.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.



# This is an incomplete and bug-ridden attempt at a chirp driver for
# the TYT MD-380 by Travis Goodspeed, KK4VCZ.  To use this plugin,
# copy or symlink it into the drivers/ directory of Chirp.


from chirp import chirp_common, directory, memmap
from chirp import bitwise
from chirp.settings import RadioSetting, RadioSettingGroup, \
    RadioSettingValueInteger, RadioSettingValueList, \
    RadioSettingValueBoolean, RadioSettingValueString, \
    RadioSettingValueFloat, InvalidValueError, RadioSettings

import logging
LOG = logging.getLogger(__name__)

# Someday I'll figure out Chinese encoding, but for now we'll stick to ASCII.
CHARSET = ["%i" % int(x) for x in range(0, 10)] + \
    [chr(x) for x in range(ord("A"), ord("Z") + 1)] + \
    [" ", ] + \
    [chr(x) for x in range(ord("a"), ord("z") + 1)] + \
    list(".,:;*#_-/&()@!?^ +") + list("\x00" * 100)
DUPLEX = ["split"];
#TODO 'DMR' should be added as a valid mode.
MODES = ["DIG", "NFM", "FM"];

# Here is where we define the memory map for the radio. Since
# We often just know small bits of it, we can use #seekto to skip
# around as needed.
#
# Large parts of this have yet to be reverse engineered, but I'm
# getting there slowly.
MEM_FORMAT = """


#seekto 0x0001ee00;
struct {
  //First byte is 62 for digital, 61 for analog
  u8 mode;  //61 for digital, 61 for nbfm, 69 for wbfm
  u8 slot;  //14 for S1, 18 for S2
  char unknown[14]; //Certainly analog or digital settings, but I don't know the bits yet.
  lbcd rxfreq[4];      //Conversion factor is unknown.
  lbcd txfreq[4];      //Stored as frequency, not offset.
  lbcd rtone[2];       //Receiver tone.
  lbcd tone[2];        //Stored as tone in tenths of a Hertz.
  char yourguess[4];

  char name[32];    //UTF16-LE
} memory[999];


#seekto 0x1200;
struct {
    char sn[8];
    char model[8];
    char code[16];
    u8 empty[8];
    lbcd prog_yr[2];
    lbcd prog_mon;
    lbcd prog_day;
    u8 empty_10f2c[4];
} info;

#seekto 0x2040;
struct {
    ul16 line0[10];
    ul16 line1[10];
} textlines;

#seekto 0x2084;
struct {
    ul32 dmrid;
//    u8 unknown0[36];
//    ul16 dmrname[16];
} identity;

"""


def do_download(radio):
    """This is your download function"""
    # NOTE: Remove this in your real implementation!
    return memmap.MemoryMap("\x00" * 262144)

    # Get the serial port connection
    serial = radio.pipe

    # Our fake radio is just a simple download of 262144 bytes
    # from the serial port. Do that one byte at a time and
    # store them in the memory map
    data = ""
    for _i in range(0, 262144):
        data = serial.read(1)

    return memmap.MemoryMap(data)


def do_upload(radio):
    """This is your upload function"""
    # NOTE: Remove this in your real implementation!
    raise Exception("This template driver does not really work!")

    # Get the serial port connection
    serial = radio.pipe

    # Our fake radio is just a simple upload of 262144 bytes
    # to the serial port. Do that one byte at a time, reading
    # from our memory map
    for i in range(0, 262144):
        serial.write(radio.get_mmap()[i])


def utftoasc(utfstring):
    """Converts a UTF16 string to ASCII by dropping the zeroes."""
    toret="";
    for c in utfstring:
        if c!='\x00':
            toret+=c;
    return toret;
def asctoutf(ascstring,size=None):
    """Converts an ASCII string to UTF16."""
    toret="";
    for c in ascstring:
        toret=toret+c+"\x00";
    if size==None: return toret;
    
    #Correct the size here.
    while len(toret)<size:
        toret=toret+"\x00";

    return toret;
    

# Uncomment this to actually register this radio in CHIRP
@directory.register
class MD380Radio(chirp_common.CloneModeRadio):
    """MD380 Binary File"""
    VENDOR = "TYT"
    MODEL = "MD-380"
    FILE_EXTENSION = "img"
    BAUD_RATE = 9600    # This is a lie.
    
    _memsize=262144
    @classmethod
    def match_model(cls, filedata, filename):
        return len(filedata) == cls._memsize
    
    
    # Return information about this radio's features, including
    # how many memories it has, what bands it supports, etc
    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_bank = False
        rf.memory_bounds = (0, 998)  # This radio supports memories 0-9
        rf.valid_bands = [(400000000, 480000000),  # Supports 70-centimeters
                          ]
        rf.valid_characters = "".join(CHARSET);
        rf.has_settings = True;
        rf.has_tuning_step = False;
        rf.has_ctone=True;
        rf.valid_modes = list(MODES);
        rf.valid_duplexes = list(DUPLEX)
        rf.valid_name_length = 16
        return rf
    
    # Processes the mmap from a file.
    def process_mmap(self):
        self._memobj = bitwise.parse(
            MEM_FORMAT, self._mmap)
    
    # Do a download of the radio from the serial port
    def sync_in(self):
        self._mmap = do_download(self)
        self._memobj = bitwise.parse(MEM_FORMAT, self._mmap)
    
    # Do an upload of the radio to the serial port
    def sync_out(self):
        do_upload(self)

    # Return a raw representation of the memory object, which
    # is very helpful for development
    def get_raw_memory(self, number):
        return repr(self._memobj.memory[number])

    # Extract a high-level memory object from the low-level memory map
    # This is called to populate a memory in the UI
    def get_memory(self, number):
        # Get a low-level memory object mapped to the image
        _mem = self._memobj.memory[number]

        # Create a high-level memory object to return to the UI
        mem = chirp_common.Memory()

        mem.number = number                 # Set the memory number
        # Convert your low-level frequency to Hertz
        #mem.freq = int(_mem.rxfreq)
        mem.freq = int(_mem.rxfreq)*10
        mem.freq = int(_mem.rxfreq)*10
        
        tone=int(_mem.tone)/10.0
        rtone=int(_mem.rtone)/10.0
        if tone!=1666.5:
            mem.ctone=tone;
        if rtone!=1666.5:
            mem.rtone=rtone;
        
        # Anything with an unset frequency is unused.
        # Maybe we should be looking at the mode instead?
        if mem.freq >500e6:
            mem.freq=400e6;
            mem.empty = True;
            return mem;
        
        mem.duplex="split"; #This radio is always split.
        mem.offset = int(_mem.txfreq)*10; #In split mode, offset is the TX freq.
        mem.name = utftoasc(str(_mem.name)).rstrip()  # Set the alpha tag
        
        mem.mode="DIG";
        rmode=_mem.mode&0x0F;
        if rmode==0x02:
            mem.mode="DIG";
        elif rmode==0x01:
            mem.mode="NFM";
        elif rmode==0x09:
            mem.mode="FM";
        else:
            print "WARNING: Mode bytes 0x%02 isn't understood for %s." % (
                _mem.mode, mem.name);

        
        return mem

    # Store details about a high-level memory to the memory map
    # This is called when a user edits a memory in the UI
    def set_memory(self, mem):
        # Get a low-level memory object mapped to the image
        _mem = self._memobj.memory[mem.number]

        # Convert to low-level frequency representation
        _mem.rxfreq = mem.freq/10;
        
        # Janky offset support.
        # TODO Emulate modes other than split.
        _mem.txfreq = mem.offset/10;
        _mem.name = asctoutf(mem.name,32);
        
        # These need to be 16665 when unused.
        _mem.tone=mem.ctone;
        _mem.rtone=mem.rtone;
        
    def get_settings(self):
        _identity = self._memobj.identity
        _info = self._memobj.info
        _textlines = self._memobj.textlines #Startup lines of text.
        
        basic = RadioSettingGroup("basic", "Basic")
        info = RadioSettingGroup("info", "Model Info")
        identity = RadioSettingGroup("identity", "Identity");
        
        #top = RadioSettings(identity, basic)
        top = RadioSettings(identity)
        identity.append(RadioSetting(
                "dmrid", "DMR Radio ID",
                RadioSettingValueInteger(0, 100000000, _identity.dmrid)));
        return top
    def set_settings(self, settings):
        _identity = self._memobj.identity
        _info = self._memobj.info
        #_bandlimits = self._memobj.bandlimits
        for element in settings:
            if not isinstance(element, RadioSetting):
                self.set_settings(element)
                continue
            if not element.changed():
                continue
            try:
                setting = element.get_name()
                #oldval = getattr(_settings, setting)
                newval = element.value
                
                #LOG.debug("Setting %s(%s) <= %s" % (setting, oldval, newval))
                setattr(_identity, setting, newval)
            except Exception, e:
                LOG.debug(element.get_name())
                raise
