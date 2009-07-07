from datetime import datetime, timedelta
from time import mktime
import os

import pysvn

from pyvcs.commit import Commit
from pyvcs.exceptions import CommitDoesNotExist, FileDoesNotExist, FolderDoesNotExist
from pyvcs.repository import BaseRepository
from pyvcs.utils import generate_unified_diff

#TODO: Fix path handling, with svn you have 2 paths, the local
# one (working local copy) and the remote (svn server).
# Local: /home/user/myrepo
# Remote: svn.myserver.com/svn/myrepo/trunk
# The problem is that remote path will be /myrepo/trunk,
# this brings problems when quering svn for file information,
# lists and logs. Assuming you are using a local working copy
# everything should more or less work fine.
class Repository(BaseRepository):
    def __init__(self, path, **kwargs):
        """
        path is the filesystem path where the repo exists, **kwargs are
        anything extra for accessing the repo
        """
        self.path = path
        self.extra = kwargs
        self.client = pysvn.Client(path)

    def _log_to_commit(self, log):
        #TODO: Trim path info, svn gives full path from url repository,
        # user may expect relative path to local copy
        commit_files = [cp_dict['path'] for cp_dict in log['changed_paths']]
        
        #TODO: Generate portable tmp paths for Client API to do its diffs
        diff = self.client.diff('/tmp/pysvndiff-', url_or_path=self.path,
                                revision1 = log['revision'])
        
        return Commit(log['revision'], log['author'],
                      datetime.fromtimestamp(log['date']), log['message'],
                      commit_files, diff)
    
    def get_commit_by_id(self, commit_id):
        """
        Returns a commit by it's id (nature of the ID is VCS dependent).
        """
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, commit_id)
        
        log_list = self.client.log(self.path, revision_start=rev, 
                                   revision_end=rev, discover_changed_paths=True)
        log = log_list.pop(0)
        
        return self._log_to_commit(log)
        

    def get_recent_commits(self, since=None):
        """
        Returns all commits since since.  If since is None returns all commits
        from the last 5 days.
        """
        if since is None:
            since = datetime.now() - timedelta(days=5)
        
        revhead = pysvn.Revision(pysvn.opt_revision_kind.head)
        
        # Convert from datetime to float (seconds since unix epoch)
        utime = mktime(since.timetuple())
        
        rev = pysvn.Revision(pysvn.opt_revision_kind.date, utime)
        
        log_list = self.client.log(self.path, revision_start=revhead, 
                                   revision_end=rev, discover_changed_paths=True)
        
        commits = [self._log_to_commit(log) for log in log_list]
        return commits

    def list_directory(self, path, revision=None):
        """
        Returns a tuple of lists of files and folders in a given directory at a
        given revision, or HEAD if revision is None.
        """
        if revision:
            rev = pysvn.Revision(pysvn.opt_revision_kind.number, revision)
        else:
            rev = pysvn.Revision(pysvn.opt_revision_kind.head)
        
        dir_path = os.path.join(self.path, path)
        
        try:
            entries = self.client.list(dir_path, revision=rev, recurse=False)
        except pysvn.ClientError: 
            raise FolderDoesNotExist
        
        files, folders = [], []
        for file_info, file_pops in entries:
            if file_info['kind'] == pysvn.node_kind.dir:
                #TODO: Path is not always present, only repos_path
                # is guaranteed, in case of looking at a remote
                # repository (with no local working copy) we should
                # check against repos_path.
                if not dir_path.startswith(file_info['path']):
                    folders.append(os.path.basename(file_info['repos_path']))
            else:
                files.append(os.path.basename(file_info['repos_path']))
            
        return files, folders

    def file_contents(self, path, revision=None):
        """
        Returns the contents of a file as a string at a given revision, or
        HEAD if revision is None.
        """
        if revision:
            rev = pysvn.Revision(pysvn.opt_revision_kind.number, revision)
        else:
            rev = pysvn.Revision(pysvn.opt_revision_kind.head)
            
        file_path = os.path.join(self.path, path)
        
        # PySVN documentation does not say what happens if the
        # file doesn't exists, hopefully it returns an exception
        # or None at least
        try:
            return self.client.cat(file_path, rev)
        except:
            raise FileDoesNotExist

