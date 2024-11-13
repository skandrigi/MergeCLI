import asyncio
from textual import events

from inference import extract_answer, get_completion
from collections import deque
from textual.reactive import reactive
from textual.widget import Widget
from textual.app import App 
from textual.widgets import Static, DirectoryTree, Button, TextArea
from textual.widgets.text_area import Selection
from textual.containers import Horizontal, Vertical, ScrollableContainer
from rich.style import Style
from rich.text import Text
from textual.widgets.text_area import TextAreaTheme

from backend.merge_conflict_manager import MergeConflictManager
from backend.conflict import ConflictDetector
from backend.resolution import StagingManager

INITIAL_TEXT = 'Print("Hello World!")'

class ScreenApp(App):
    CSS_PATH = "boxes.tcss"
    BINDINGS = [
        ("i", f"fix_merge('incoming')", "Resolve Incoming Conflict"),
        ("c", f"fix_merge('current')", "Resolve Current Conflict"),
        ("b", f"fix_merge('both')", "Resolve Both Conflicts")
    ]
    flavor = Text("Edit a merge conflict to get started! ", style="white")
    flavor.append("\U000015E3 ", style="#1C6FFF")
    comment_content = reactive(flavor)

    def __init__(self, openai_api_key=None):
        # Backend initialization
        super().__init__()
        self.conflict_manager = MergeConflictManager(conflicts_folder="cli/merge-conflicts")
        self.conflict_detector = ConflictDetector()
        self.staging_manager = StagingManager()
        self.changes = []
        self.path = "."
        # Optionally, initialize OpenAI client here if needed for AI conflict resolution
        # self.openai_client = OpenAIClient(openai_api_key) if openai_api_key else None
    
    def compose(self):
        # Define UI components
        self.widget = Static("<<< MERGE 🍒", id="header-widget")
        self.files = DirectoryTree("./", id="file-browser", classes="grid")
        self.code = TextArea.code_editor(INITIAL_TEXT, language="python", read_only=True, id="code-view", classes="grid", theme="dracula")
        dracula = TextAreaTheme.get_builtin_theme("dracula")
        my_theme = TextAreaTheme(
            name="pacs",
            base_style=Style(bgcolor="#28233B"),
            cursor_style=Style(color="white", bgcolor="blue"),
            syntax_styles={
                **dracula.syntax_styles,
                "string": Style(color="#FFABAB"),
                "comment": Style(color="#FFD153"),
                "function": Style(color="#FFD153")
            }
        )
        self.code.register_theme(my_theme)
        self.code.theme = "pacs"
        self.comment = TextArea.code_editor("", read_only=True, classes="grid", theme="dracula")
        self.popup = Static("This is a temporary pop-up!", id="popup", classes="popup")

        yield self.widget
        yield self.files
        # yield ScrollableContainer((self.code))
        yield self.code
        yield self.comment
        yield self.popup
        with Horizontal(id="button-container"):
            self.resolve_button = Button("\U000015E3 Accept (I)ncoming", id="resolve-button", classes="action-button", disabled=True)
            self.accept_curr_button = Button("\U00002B24 Accept (C)urrent", id="acceptcurr-button", classes="action-button", disabled=True)
            self.accept_both_button = Button("🍓 Accept (B)oth", id="acceptboth-button", classes="action-button", disabled=True)
            
            yield self.resolve_button
            yield self.accept_curr_button
            yield self.accept_both_button


    def on_mount(self) -> None:
        # Set up initial view titles and styles
        files_title = Text("", style="white")
        files_title.append("FILES", style="white")
        self.files.border_title = files_title
        self.files.border_title_align = "left"
        
        code_title = Text("", style="white")
        code_title.append("C", style="white")
        code_title.append("\U00002b24", style="#FFABAB")
        code_title.append("DE", style="white")
        self.code.border_title = code_title
        self.code.border_title_align = "left"

        # Title for Comment View
        comment_title = Text("", style="white")
        comment_title.append("C", style="white")
        comment_title.append("\U00002b24", style="#FFABAB")
        comment_title.append("MMENTS", style="white")
        self.comment.border_title = comment_title 
        self.comment.border_title_align = "left"

    def action_fix_merge(self, type):
        if len(self.changes) == 0:
            return
        if type in ("current", "incoming", "both"):
            self.staging_manager.resolve_and_save(type, self.path)
            self.changes = self.changes[1:]
            with open(self.path, "r") as file: content = file.read()

            code_view = self.query_one("#code-view")
            code_view.text = content

            if(len(self.changes) == 0):
                resolved_popup = Text("", style="white")
                resolved_popup.append("🍊 Merge conflict ", style="white")
                resolved_popup.append("resolved!", style="#A6E1E5")
                self.show_temp_popup(resolved_popup)
            else:
                asyncio.create_task(self.define_commits(content, self.path))
        else:
            print("invalid type")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if len(self.changes) == 0:
            return
        if event.button.id == "resolve-button":
            self.staging_manager.resolve_and_save("incoming", self.path)
            self.changes = self.changes[1:]
        elif event.button.id == "acceptcurr-button":
            self.staging_manager.resolve_and_save("current", self.path)
            self.changes = self.changes[1:]
        elif event.button.id == "acceptboth-button":
            self.staging_manager.resolve_and_save("both", self.path)
            self.changes = self.changes[1:]
        with open(self.path, "r") as file:
                content = file.read()
        code_view = self.query_one("#code-view")
        code_view.text = content
        if(len(self.changes) == 0):
            resolved_popup = Text("", style="white")
            resolved_popup.append("🍊 Merge conflict ", style="white")
            resolved_popup.append("resolved!", style="#A6E1E5")
            self.show_temp_popup(resolved_popup)
        else:
            asyncio.create_task(self.define_commits(content, self.path))

    async def define_commits(self, file_content, path):
        """Retrieve and display commit information asynchronously."""
        completion = await get_completion(file_content)
        answers = extract_answer(completion)
        if path == self.path:
            self.comment_content += "\n\n" + "\n\n".join(answers)

    # def watch_comment_content(self, old_comment: str, new_comment: str) -> None:  
    #     print("Hello")
    #     self.comment.update(new_comment)

    def watch_comment_content(self, old_comment: str, new_comment: str) -> None:
        print("Hello")
        self.comment.text = str(new_comment)  # Set the new text
        self.comment.refresh()  # Refresh to ensure the UI updates

    async def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Display selected file content and detect conflicts."""
        event.stop()
        file_path = str(event.path)
        self.path = file_path

        with open(file_path, "r") as file:
            content = file.read()

        code_view = self.query_one("#code-view")
        code_view.text = content

        try:
            if "<<<<<<<" in content and "=======" in content and ">>>>>>>" in content:
                self.resolve_button.disabled = False
                self.accept_curr_button.disabled = False
                self.accept_both_button.disabled = False
                conflict_sections = self.conflict_detector.parse_conflict_sections(content)
                
                conflict_text = "\n\n".join(
                    f"🔥🔥🔥 --- Conflict Section {i+1} --- 🔥🔥🔥\n"
                    f"🔥 Current changes:\n{''.join(line + '\n' for line in section['current'][1])}\n"
                    f"🔥 Incoming changes:\n{''.join(line + '\n' for line in section['incoming'][1])}\n"
                    for i, section in enumerate(conflict_sections)
                )

                self.changes = conflict_sections
                self.comment_content = conflict_text
                asyncio.create_task(self.define_commits(content, file_path))
            else:
                self.comment_content = "No conflicts detected in this file."
        except Exception as e:
            self.comment_content = f"Error loading file: {e}"

    def show_temp_popup(self, message):
        """Display a temporary popup with a message."""
        popup = self.query_one("#popup", Static)
        popup.styles.opacity = 1.0
        popup.update(message)
        popup.styles.opacity = 1
        popup.styles.display = "block" 
        self.set_timer(2, lambda: self.hide_temp_popup())

    def hide_temp_popup(self):
        """Hide the temporary popup."""
        popup = self.query_one("#popup", Static)
        popup.styles.animate("opacity", value=0.0, duration=2.0)
        self.set_timer(1.7, lambda: setattr(popup.styles, "display", "none"))
        

if __name__ == "__main__":
    app = ScreenApp(openai_api_key="your_openai_api_key_here")
    app.run()
