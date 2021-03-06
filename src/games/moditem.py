from PyQt4 import QtGui
import util
import client
import os

# Maps names of featured mods to ModItem objects.
mods = {}

mod_crucial = ["balancetesting", "faf"]

# These mods are not shown in the game list
mod_invisible = []

mod_favourites = []  # LATER: Make these saveable and load them from settings

class ModItem(QtGui.QListWidgetItem):
    def __init__(self, message, *args, **kwargs):
        QtGui.QListWidgetItem.__init__(self, *args, **kwargs)

        self.mod  = message["name"]
        self.name = message["fullname"]
        #Load Icon and Tooltip

        tip = message["desc"]      
        self.setToolTip(tip)

        icon = util.icon(os.path.join("games/mods/", self.mod + ".png"))
        if icon.isNull():
            icon = util.icon("games/mods/default.png")
        self.setIcon(icon)

        if  self.mod in mod_crucial:
            color = client.instance.getColor("self")
        else:
            color = client.instance.getColor("player")
            
        self.setTextColor(QtGui.QColor(color))
        self.setText(self.name)


    def __ge__(self, other):
        ''' Comparison operator used for item list sorting '''        
        return not self.__lt__(other)
    
    
    def __lt__(self, other):
        ''' Comparison operator used for item list sorting '''        
        
        # Crucial Mods are on top
        if self.mod in mod_crucial and other.mod in mod_crucial:
            return mod_crucial.index(self.mod) < mod_crucial.index(other.mod)
        if self.mod in mod_crucial and other.mod not in mod_crucial:
            return True
        if self.mod not in mod_crucial and other.mod in mod_crucial:
            return False
        
        # Favourites are also ranked up top
        if (self.mod in mod_favourites) and not (other.mod in mod_favourites): return True
        if not(self.mod in mod_favourites) and (other.mod in mod_favourites): return False
        
        # Default: Alphabetical
        return self.name.lower() < other.mod.lower()
    



