# -*- coding: utf-8 -*-
#
# GPL License and Copyright Notice ============================================
#  This file is part of Wrye Bash.
#
#  Wrye Bash is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  Wrye Bash is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Wrye Bash; if not, write to the Free Software Foundation,
#  Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
#  Wrye Bash copyright (C) 2005-2009 Wrye, 2010-2015 Wrye Bash Team
#  https://github.com/wrye-bash
#
# =============================================================================

import os

from .. import balt
from .. import bass
from .. import bolt
from .. import bosh
from .. import bush
from .. import env
import wx
import wx.wizard as wiz

from ..boop import Installer, MissingDependency


class WizardReturn(object):
    __slots__ = ('cancelled', 'install_files', 'page_size', 'pos')

    def __init__(self):
        # cancelled: true if the user canceled or if an error occurred
        self.cancelled = False
        # install_files: file->dest mapping of files to install
        self.install_files = bolt.LowerDict()
        # page_size: Tuple/wxSize of the saved size of the Wizard
        self.page_size = balt.defSize
        # pos: Tuple/wxPoint of the saved position of the Wizard
        self.pos = balt.defPos


class InstallerFomod(wiz.Wizard):
    def __init__(self, parent_window, installer, page_size, pos):
        style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX
        wiz.Wizard.__init__(self, parent_window, title=_(u'Fomod Installer'),
                            pos=pos, style=style)

        # 'dummy' page tricks the wizard into always showing the "Next" button
        self.dummy = wiz.PyWizardPage(self)
        self.next = None

        # True prevents actually moving to the 'next' page.
        # We use this after the "Next" button is pressed,
        # while the parser is running to return the _actual_ next page
        self.block_change = True
        # 'finishing' is to allow the "Next" button to be used
        # when it's name is changed to 'Finish' on the last page of the wizard
        self.finishing = False

        fomod_files = installer.fomod_files()
        info_path = fomod_files[0]
        if info_path is not None:
            info_path = info_path.s
        conf_path = fomod_files[1].s
        data_path = bass.dirs['mods']
        ver = env.get_file_version(bass.dirs['app'].join(bush.game.exe).s)
        game_ver = u'.'.join([unicode(i) for i in ver])
        self.parser = Installer((info_path, conf_path), dest=data_path,
                                game_version=game_ver)

        self.is_archive = isinstance(installer, bosh.InstallerArchive)
        if self.is_archive:
            self.archive_path = bass.getTempDir()
        else:
            self.archive_path = bass.dirs['installers'].join(installer.archive)

        # Intercept the changing event so we can implement 'block_change'
        self.Bind(wiz.EVT_WIZARD_PAGE_CHANGING, self.on_change)
        self.ret = WizardReturn()
        self.ret.page_size = page_size

        # So we can save window size
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wiz.EVT_WIZARD_CANCEL, self.on_close)
        self.Bind(wiz.EVT_WIZARD_FINISHED, self.on_close)

        # Set the minimum size for pages, and setup on_size to resize the
        # First page to the saved size
        self.SetPageSize((600, 500))
        self.first_page = True

    # bain expects a "relative dest file" -> "relative src file"
    # mapping to install. Fomod only provides relative dest folders and some
    # sources are folders too, requiring this little hack
    @staticmethod
    def _process_fomod_dict(files_dict, src_dir):
        final_dict = bolt.LowerDict()
        src_dir_path = src_dir.s
        for src, dest in files_dict.iteritems():
            dest = bolt.Path(dest)
            src_full = src_dir.join(src)
            src_full_path = src_full.s
            if src_full.isdir():
                for (dirpath, _, fnames) in os.walk(src_full_path):
                    for fname in fnames:
                        file_src_full = os.path.join(dirpath, fname)
                        file_src = os.path.relpath(file_src_full, src_dir_path)
                        file_dest = dest.join(os.path.relpath(file_src_full,
                                                              src_full_path))
                        final_dict[file_dest.s] = file_src
            else:
                final_dict[dest.s] = src
        return final_dict

    def on_close(self, event):
        if not self.IsMaximized():
            # Only save the current size if the page isn't maximized
            self.ret.page_size = self.GetSize()
            self.ret.pos = self.GetPosition()
        event.Skip()

    def on_size(self, event):
        if self.first_page:
            # On the first page, resize it to the saved size
            self.first_page = False
            self.SetSize(self.ret.page_size)
        else:
            # Otherwise, regular resize, save the size if we're not
            # maximized
            if not self.IsMaximized():
                self.ret.page_size = self.GetSize()
                self.pos = self.GetPosition()
            event.Skip()

    def on_change(self, event):
        if event.GetDirection():
            if not self.finishing:
                # Next, continue script execution
                if self.block_change:
                    # Tell the current page that next was pressed,
                    # So the parser can continue parsing,
                    # Then show the page that the parser returns,
                    # rather than the dummy page
                    event.GetPage().on_next()
                    event.Veto()
                    self.block_change = False
                else:
                    self.block_change = True
                    return
        else:
            # Previous, pop back to the last state,
            # and resume execution
            self.finishing = False
            event.Veto()
            answer = {'previous_step': True}
            self.parser.send(answer)
            self.block_change = False
        try:
            step = next(self.parser)
            self.next = PageSelect(self, step['name'], step['groups'])
        except StopIteration:
            self.next = None
        self.ShowPage(self.next)

    def run(self):
        try:
            self.parser.send(None)
        except MissingDependency as exc:
            page = PageError(self, "Missing Dependency", str(exc))
        else:
            step = next(self.parser)
            page = PageSelect(self, step['name'], step['groups'])
        self.ret.cancelled = not self.RunWizard(page)
        install_files = bolt.LowerDict(self.parser.collected_files)
        self.ret.install_files = self._process_fomod_dict(install_files,
                                                          self.archive_path)
        # Clean up temp files
        if self.is_archive:
            try:
                bass.rmTempDir()
            except Exception:
                pass
        return self.ret


# PageInstaller ----------------------------------------------
#  base class for all the parser wizard pages, just to handle
#  a couple simple things here
# ------------------------------------------------------------
class PageInstaller(wiz.PyWizardPage):
    def __init__(self, parent):
        wiz.PyWizardPage.__init__(self, parent)
        self.parent = parent
        self._enableForward(True)

    def _enableForward(self, enable):
        self.parent.FindWindowById(wx.ID_FORWARD).Enable(enable)

    def GetNext(self):
        return self.parent.dummy

    def GetPrev(self):
        return self.parent.dummy

    def on_next(self):
        # This is what needs to be implemented by sub-classes,
        # this is where flow control objects etc should be
        # created
        pass


# PageError --------------------------------------------------
#  Page that shows an error message, has only a "Cancel"
#  button enabled, and cancels any changes made
# -------------------------------------------------------------
class PageError(PageInstaller):
    def __init__(self, parent, title, error_msg):
        PageInstaller.__init__(self, parent)

        # Disable the "Finish"/"Next" button
        self._enableForward(False)

        # Layout stuff
        sizer_main = wx.FlexGridSizer(2, 1, 5, 5)
        text_error = balt.RoTextCtrl(self, error_msg, autotooltip=False)
        sizer_main.Add(balt.StaticText(parent, label=title))
        sizer_main.Add(text_error, 0, wx.ALL | wx.CENTER | wx.EXPAND)
        sizer_main.AddGrowableCol(0)
        sizer_main.AddGrowableRow(1)
        self.SetSizer(sizer_main)
        self.Layout()

    def GetNext(self):
        return None

    def GetPrev(self):
        return None


# PageSelect -------------------------------------------------
#  A Page that shows a message up top, with a selection box on
#  the left (multi- or single- selection), with an optional
#  associated image and description for each option, shown when
#  that item is selected
# ------------------------------------------------------------
class PageSelect(PageInstaller):
    def __init__(self, parent, step_name, list_groups):
        PageInstaller.__init__(self, parent)

        # ListBox -> (group_id, group_type)
        self.box_group_map = {}
        # ListBox -> [(option_id, option_type, option_desc, option_img), ...]
        self.box_option_map = {}

        sizer_main = wx.FlexGridSizer(2, 1, 0, 0)
        sizer_main.Add(balt.StaticText(self, step_name))
        sizer_content = wx.GridSizer(1, 2, 0, 0)

        sizer_extra = wx.GridSizer(2, 1, 0, 0)
        self.bmp_item = balt.Picture(self, 0, 0, background=None)
        self.text_item = balt.RoTextCtrl(self, autotooltip=False)
        sizer_extra.Add(self.bmp_item, 1, wx.ALL | wx.EXPAND)
        sizer_extra.Add(self.text_item, 1, wx.EXPAND | wx.ALL)

        sizer_groups = wx.GridSizer(len(list_groups), 1, 0, 0)
        for group in list_groups:
            sizer_group = wx.FlexGridSizer(2, 1, 0, 0)
            sizer_group.Add(balt.StaticText(self, group['name']))

            if group['type'] == 'SelectExactlyOne':
                list_type = 'list'
            else:
                list_type = 'checklist'
            list_box = balt.listBox(self, kind=list_type, isHScroll=True,
                                    onSelect=self.on_select,
                                    onCheck=self.on_check)
            self.box_group_map[list_box] = (group['id'], group['type'])
            self.box_option_map[list_box] = []

            for option in group['plugins']:
                idx = list_box.Append(option['name'])
                if option['type'] in ('Recommended', 'Required'):
                    if group['type'] == 'SelectExactlyOne':
                        list_box.SetSelection(idx)
                    else:
                        list_box.Check(idx, True)
                        self.check(list_box, idx)
                self.box_option_map[list_box].append((option['id'],
                                                      option['type'],
                                                      option['description'],
                                                      option['image']))

            if group['type'] == 'SelectExactlyOne':
                list_box.SetSelection(list_box.GetSelection() or 0)
            elif group['type'] == 'SelectAtLeastOne':
                if not list_box.GetChecked():
                    list_box.Check(0, True)
            elif group['type'] == 'SelectAll':
                for idx in xrange(0, list_box.GetCount()):
                    list_box.Check(idx, True)

            if list_groups.index(group) == 0:
                self.select(list_box, list_box.GetSelection() or 0)

            sizer_group.Add(list_box, 1, wx.EXPAND | wx.ALL)
            sizer_group.AddGrowableRow(1)
            sizer_group.AddGrowableCol(0)
            sizer_groups.Add(sizer_group, wx.ID_ANY, wx.EXPAND)

        sizer_content.Add(sizer_groups, wx.ID_ANY, wx.EXPAND)
        sizer_content.Add(sizer_extra, wx.ID_ANY, wx.EXPAND)
        sizer_main.Add(sizer_content, wx.ID_ANY, wx.EXPAND)
        sizer_main.AddGrowableRow(1)
        sizer_main.AddGrowableCol(0)

        self.SetSizer(sizer_main)
        self.Layout()

    # Handles option type
    def check_option(self, box, idx, check=True):
        option_type = self.box_option_map[box][idx][1]
        if check and option_type == 'NotUsable':
            box.Check(idx, False)
        elif not check and option_type == 'Required':
            box.Check(idx, True)
        else:
            box.Check(idx, check)

    # Handles group type
    def check(self, box, idx):
        group_type = self.box_group_map[box][1]
        self.check_option(box, idx, box.IsChecked(idx))

        if group_type == 'SelectAtLeastOne':
            if not box.IsChecked(idx) and len(box.GetChecked()) == 0:
                box.Check(idx, True)
        elif group_type == 'SelectAtMostOne':
            checked = box.GetChecked()
            if box.IsChecked(idx) and len(checked) > 1:
                checked = (a for a in checked if a != idx)
                for i in checked:
                    self.check_option(box, i, False)
        elif group_type == 'SelectAll':
            box.Check(idx, True)

    def on_check(self, event):
        idx = event.GetInt()
        box = event.GetEventObject()
        self.check(box, idx)

    def select(self, box, idx):
        box.SetSelection(idx)
        option = self.box_option_map[box][idx]
        self._enableForward(True)
        self.text_item.SetValue(option[2])
        # Don't want the bitmap to resize until we call self.Layout()
        self.bmp_item.Freeze()
        img = self.parent.archive_path.join(option[3])
        if img.isfile():
            image = wx.Bitmap(img.s)
            self.bmp_item.SetBitmap(image)
            self.bmp_item.SetCursor(wx.StockCursor(wx.CURSOR_MAGNIFIER))
        else:
            self.bmp_item.SetBitmap(None)
            self.bmp_item.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))
        self.bmp_item.Thaw()

    def on_select(self, event):
        idx = event.GetInt()
        box = event.GetEventObject()
        self.select(box, idx)

    def on_next(self):
        answer = {}

        for box, group in self.box_group_map.iteritems():
            group_id = group[0]
            group_type = group[1]
            answer[group_id] = []
            if group_type == 'SelectExactlyOne':
                idx = box.GetSelection()
                answer[group_id] = [self.box_option_map[box][idx][0]]
            else:
                for idx in box.GetChecked():
                    answer[group_id].append(self.box_option_map[box][idx][0])

            idx_num = len(answer[group_id])
            if group_type == 'SelectExactlyOne' and idx_num != 1:
                raise ValueError("Must select exatly one.")
            elif group_type == 'SelectAtMostOne' and idx_num > 1:
                raise ValueError("Must select at most one.")
            elif group_type == 'SelectAtLeast' and idx_num < 1:
                raise ValueError("Must select at most one.")
            elif (group_type == 'SelectAll'
                    and idx_num != len(self.box_option_map[box])):
                raise ValueError("Must select at most one.")

        self.parent.parser.send(answer)
