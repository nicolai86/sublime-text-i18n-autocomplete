import sublime
import sublime_plugin
import os
import re
import time
import subprocess
import json
import datetime, calendar

PLUGIN_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
HELPER_DIRECTORY = PLUGIN_DIRECTORY + '/'
FLAT_YAML_KEYS = HELPER_DIRECTORY + 'flat_yaml_keys.rb'

# stolen from https://github.com/alienhard/SublimeAllAutocomplete
# limits to prevent bogging down the system
MIN_WORD_SIZE = 3
MAX_WORD_SIZE = 50

MAX_VIEWS = 20
MAX_WORDS_PER_VIEW = 100
MAX_FIX_TIME_SECS_PER_VIEW = 0.01

class YamlChecker:
    def __init__(self, locale_path):
        self.locale_path = locale_path
        self.keys = []

    def reload(self):
        self.timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()
        self.keys = self.yaml_keys()

    def yaml_keys(self):
        command = ['ruby', FLAT_YAML_KEYS, self.locale_path]
        json_keys = subprocess.check_output(command).decode("utf-8")
        return json.loads(json_keys)

class CorrectAutoCompletionCommand(sublime_plugin.TextCommand):
    def run(self, edit, col=None):
        """
            replaces the content of a quoted string with a somestring, indentified using the start index
            e.g. "keykey.foo" can be replaced to "key.foo"

            this is necessary because sublime's autocompletion inserts the value rather than replaces what's already there.
        """
        view = sublime.active_window().active_view()
        sel = view.sel()[0].a

        (row, _) = view.rowcol(sel)
        line = view.substr(view.line(sel))

        end_index = line.find("'", col)
        if end_index == -1:
            end_index = line.find('"', col)
        start_index = line.rfind("'", 0, col)
        if start_index == -1:
            start_index = line.rfind('"', 0, col)

        completion = line[col:end_index]

        start_point = self.view.text_point(row, start_index + 1)
        end_point = self.view.text_point(row, end_index)

        region = sublime.Region(start_point, end_point)
        view.replace(edit, region, completion)

class RubyI18nAutocomplete(sublime_plugin.EventListener):
    def on_activated(self, view):
        self.key_loader = YamlChecker(self.locale_path())
        self.key_loader.reload()
        self.completion_start_col = None

    def on_commit_completion(self):
        print("foo")

    def on_post_text_command(self, view, command_name, args):
        if command_name != "commit_completion":
            return None

        valid_scopes = self.get_setting('ri18n_valid_scopes',view)
        sel = view.sel()[0].a

        if not any(s in view.scope_name(sel) for s in valid_scopes):
            return None

        if self.completion_start_col:
            view.run_command("correct_auto_completion", { 'col': self.completion_start_col })
            self.completion_start_col = None

    def get_setting(self, string, view=None):
        if view and view.settings().get(string):
            return view.settings().get(string)
        else:
            return sublime.load_settings('i18n.sublime-settings').get(string)

    def locale_path(self):
        locales_directory = ''
        for path in sublime.active_window().folders():
            locales_directory = path + '/config/locales'
            break
        return locales_directory

    def quoted_string_region(self, view):
        sel = view.sel()[0].a
        line = view.substr(view.line(sel))
        (row, col) = view.rowcol(sel)

        end_index = line.find("'", col)
        if end_index == -1:
            end_index = line.find('"', col)

        start_index = line.rfind("'", 0, col)
        if start_index == -1:
            start_index = line.rfind('"', 0, col)

        return (start_index, end_index, col)

    def on_query_completions(self, view, prefix, locations):
        # don't do anything unless we are inside ruby strings
        valid_scopes = self.get_setting('ri18n_valid_scopes',view)
        sel = view.sel()[0].a

        # don't do anything if we have nothing
        if len(self.key_loader.keys) == 0:
            return []

        if not any(s in view.scope_name(sel) for s in valid_scopes):
            return []

        line = view.substr(view.line(sel))
        (start_index, end_index, col) = self.quoted_string_region(view)
        quoted_string = line[start_index+1:end_index]
        self.completion_start_col = col - len(prefix)

        words = self.word_completion(view, prefix, locations)

        for key in self.key_loader.keys:
            if key.startswith(quoted_string) or len(quoted_string) == 0:
                words.append(key)

        matches = [(w, w) for w in words]
        return matches

    # all word completion plugin... might be deleted later on
    #
    #
    def word_completion(self, view, prefix, locations):
        words = []

        # Limit number of views but always include the active view. This
        # view goes first to prioritize matches close to cursor position.
        other_views = [v for v in sublime.active_window().views() if v.id != view.id]
        views = [view] + other_views
        views = views[0:MAX_VIEWS]

        for v in views:
            if len(locations) > 0 and v.id == view.id:
                view_words = v.extract_completions(prefix, locations[0])
            else:
                view_words = v.extract_completions(prefix)
            view_words = self.filter_words(view_words)
            view_words = self.fix_truncation(v, view_words)
            words += view_words

        words = self.without_duplicates(words)
        return words

    def filter_words(self, words):
        words = words[0:MAX_WORDS_PER_VIEW]
        return [w for w in words if MIN_WORD_SIZE <= len(w) <= MAX_WORD_SIZE]

    # keeps first instance of every word and retains the original order
    # (n^2 but should not be a problem as len(words) <= MAX_VIEWS*MAX_WORDS_PER_VIEW)
    def without_duplicates(self, words):
        result = []
        for w in words:
            if w not in result:
                result.append(w)
        return result


    # Ugly workaround for truncation bug in Sublime when using view.extract_completions()
    # in some types of files.
    def fix_truncation(self, view, words):
        fixed_words = []
        start_time = time.time()

        for i, w in enumerate(words):
            #The word is truncated if and only if it cannot be found with a word boundary before and after

            # this fails to match strings with trailing non-alpha chars, like
            # 'foo?' or 'bar!', which are common for instance in Ruby.
            match = view.find(r'\b' + re.escape(w) + r'\b', 0)
            truncated = match.empty()
            if truncated:
                #Truncation is always by a single character, so we extend the word by one word character before a word boundary
                extended_words = []
                view.find_all(r'\b' + re.escape(w) + r'\w\b', 0, "$0", extended_words)
                if len(extended_words) > 0:
                    fixed_words += extended_words
                else:
                    # to compensate for the missing match problem mentioned above, just
                    # use the old word if we didn't find any extended matches
                    fixed_words.append(w)
            else:
                #Pass through non-truncated words
                fixed_words.append(w)

            # if too much time is spent in here, bail out,
            # and don't bother fixing the remaining words
            if time.time() - start_time > MAX_FIX_TIME_SECS_PER_VIEW:
                return fixed_words + words[i+1:]

        return fixed_words