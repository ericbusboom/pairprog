from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.buffer import Buffer

def main():
    # Key bindings
    kb = KeyBindings()

    @kb.add('enter')
    def enter_handler(event):
        # Append text from the input field to the history buffer
        history_buffer.text += input_field.text + '\n'
        # Clear the input field after copying text
        input_field.buffer.reset()

    # Create a buffer for the history area (top area)
    history_buffer = Buffer()

    # Create the history window (top area)
    history_window = Window(content=TextArea(history_buffer, read_only=True), height=5)

    # Create the input text area (bottom area)
    input_field = TextArea(height=5, multiline=False, prompt='>> ')

    # Layout
    layout = Layout(HSplit([history_window, input_field]))

    # Application
    app = Application(layout=layout, key_bindings=kb, full_screen=True)

    app.run()

if __name__ == "__main__":
    main()
