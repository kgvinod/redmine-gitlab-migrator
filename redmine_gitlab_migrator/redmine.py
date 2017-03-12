from itertools import chain
import re
import urllib.request
import os


from . import APIClient, Project

ANONYMOUS_USER_ID = 2

class RedmineClient(APIClient):
    PAGE_MAX_SIZE = 100

    def get_auth_headers(self):
        return {"X-Redmine-API-Key": self.api_key}

    def get(self, *args, **kwargs):
        # In detail views, redmine encapsulate "foo" typed objects under a
        # "foo" key on the JSON.
        ret = super().get(*args, **kwargs)
        values = ret.values()
        if len(values) == 1:
            return list(values)[0]
        else:
            return ret

    def unpaginated_get(self, *args, **kwargs):
        """ Iterates over API pagination for a given resource list
        """
        kwargs['params'] = kwargs.get('params', {})
        kwargs['params']['limit'] = self.PAGE_MAX_SIZE

        resp = self.get(*args, **kwargs)

        # Try to autofind the top-level key containing
        keys_candidates = (
            set(resp.keys()) - set(['total_count', 'offset', 'limit']))

        assert len(keys_candidates) == 1
        res_list_key = list(keys_candidates)[0]

        result_pages = [resp[res_list_key]]
        if 'offset' not in resp:
            raise ValueError('HTTP response data is not paginated')

        while (resp['total_count'] - resp['offset'] - resp['limit']) > 0:
            kwargs['params']['offset'] = (kwargs['params'].get('offset', 0)
                                          + self.PAGE_MAX_SIZE)
            resp = self.get(*args, **kwargs)
            result_pages.append(resp[res_list_key])
        return chain.from_iterable(result_pages)


class RedmineProject(Project):
    
    
    REGEX_PROJECT_URL = re.compile(
        r'^(?P<base_url>https?://.*)/projects/(?P<project_name>[\w_-]+)$')

    REGEX_CATEGORY_PROJECT_URL = re.compile(
        r'^(?P<base_url>https?://.*)/project/(?P<category_name>[\w_-]+)/(?P<project_name>[\w_-]+)/?$')

    def __init__(self, url, *args, **kwargs):
        normalized_url = self._canonicalize_url(url)
        print ("normalized url=" + normalized_url)
        super().__init__(normalized_url, *args, **kwargs)
        self.api_url = '{}.json'.format(self.public_url)
        print ("api url=" + self.api_url)
        self.instance_url = self._url_match.group('base_url')
        print ("instance url=" + self.instance_url)
        self.api_key = args[0].api_key
        print ("api key=" + self.api_key)
        self.All_Issue_List = []

    @classmethod
    def _canonicalize_url(cls, url):
        """ If using caterogies, return the category-less URL

        eg:
          - category URL: https://example.com/project/dev/foobar/
          - category-less URL: https://example.com/projects/foobar/

        API endpoints are reachable only for category-less URLs.
        """
        m = cls.REGEX_CATEGORY_PROJECT_URL.match(url)
        if m:
            return '{base_url}/projects/{project_name}'.format(**m.groupdict())
        else:
            return url

    def get_all_issues(self):
    
        if len(self.All_Issue_List) > 0:
            return self.All_Issue_List
    
        print ("@@@ ENTRY redmine::get_all_issues")    
        
        issues = self.api.unpaginated_get(
            '{}/issues.json?status_id=*'.format(self.public_url))
        detailed_issues = []
        # It's impossible to get issue history from list view, so get it from
        # detail view...

        count = 0 
        d_folder = "downloads"
        
        for issue_id in (i['id'] for i in issues):
            issue_url = '{}/issues/{}.json?include=journals,watchers,relations,childrens,attachments'.format(
                self.instance_url, issue_id)
                
            count += 1
            if count > 20:
                self.All_Issue_List = detailed_issues
                return detailed_issues  
            
            issue = self.api.get(issue_url)
            print ("@@@@ got issue with id=" + str(issue['id']))   
            #print (issue) 

            attachments = issue["attachments"]
            for attachment in attachments:
                print ("@@@@@ attachment=" + attachment["filename"])

                issue_d_folder = os.path.join(d_folder, str(issue_id));
                if not os.path.exists(os.path.join(issue_d_folder)):
                    os.makedirs(issue_d_folder)
                dl_file = os.path.join(issue_d_folder, attachment["filename"]);
                urllib.request.urlretrieve (attachment["content_url"] +"?key=" + self.api_key, dl_file)

                attachment["local_file"] = dl_file;

            detailed_issues.append(issue)
            
        print ("@@@ EXIT redmine::get_all_issues")
        self.All_Issue_List = detailed_issues
        return detailed_issues

    def get_participants(self):
        """Get participating users (issues authors/owners)

        :return: list of all users participating on issues
        :rtype: list
        """
        
        print ("@@@ ENTRY redmine::get_participants")
            
        user_ids = set()
        users = []
        # FIXME: cache
        
        print ("@@@@ get all issues")
        all_issues = self.get_all_issues()
        print ("@@@@ # of issues=" + str(len(all_issues)))
                
        for i in all_issues:
            for i in chain(i.get('watchers', []),
                           [i['author'], i.get('assigned_to', None)]):

                if i is None:
                    continue
                user_ids.add(i['id'])

        for i in user_ids:
            # The anonymous user is not really part of the project...
            if i != ANONYMOUS_USER_ID:
                users.append(self.api.get('{}/users/{}.json'.format(
                    self.instance_url, i)))
                    
        print ("@@@@ # of participants=" + str(len(users)))   
        print ("@@@ EXIT redmine::get_participants")                 
        return users

    def get_users_index(self):
        """ Returns dict index of users (by user id)
        """
        return {i['id']: i for i in self.get_participants()}

    def get_versions(self):
        response = self.api.get('{}/versions.json'.format(self.public_url))
        return response['versions']
