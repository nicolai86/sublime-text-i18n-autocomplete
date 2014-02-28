import sublime
import sublime_plugin
import os

import re
import time

# stolen from https://github.com/alienhard/SublimeAllAutocomplete
# limits to prevent bogging down the system
MIN_WORD_SIZE = 3
MAX_WORD_SIZE = 50

MAX_VIEWS = 20
MAX_WORDS_PER_VIEW = 100
MAX_FIX_TIME_SECS_PER_VIEW = 0.01

class RubyI18nAutocomplete(sublime_plugin.EventListener):
    def on_activated(self,view):
        self.size = view.size()

    def on_query_context(self, view, key, operator, operand, match_all):
        sel = view.sel()[0]
        if not sel or sel.empty():
            return None

        valid_scopes = self.get_setting('ri18n_valid_scopes', view)
        if not any(s in view.scope_name(sel) for s in valid_scopes):
            return None

        print("on_query_context")

        valid = sel.empty()
        return valid == operand

    # def on_selection_modified(self, view):
    #     if not view.window():
    #         return

    #     sel = view.sel()[0]
    #     if not sel or sel.empty():
    #         return

    #     valid_scopes = self.get_setting('ri18n_valid_scopes', view)
    #     if not any(s in view.scope_name(sel) for s in valid_scopes):
    #         return

    #     print("on_selection_modified")
    #     if sel.empty():
    #         print(view.substr(sel))
    #         # if len(view.extract_scope(sel.a)) < 3:
    #         #     view.run_command('auto_complete',
    #         #     {'disable_auto_insert': True,
    #         #     'next_completion_if_showing': False})

    def get_setting(self,string,view=None):
        if view and view.settings().get(string):
            return view.settings().get(string)
        else:
            return sublime.load_settings('i18n.sublime-settings').get(string)

    def on_query_completions(self, view, prefix, locations):
        # don't do anything unless we are inside ruby strings
        valid_scopes = self.get_setting('ri18n_valid_scopes',view)
        sel = view.sel()[0].a

        if not any(s in view.scope_name(sel) for s in valid_scopes):
            return []

        # TODO yaml stuff
        current_path = view.file_name()
        for path in sublime.active_window().folders():
            current_path = current_path.replace(path + '/', '')

        words = self.word_completion(view, prefix, locations)
        words.append(current_path)
        matches = [(w, w.replace('$', '\\$')) for w in words]
        return matches

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