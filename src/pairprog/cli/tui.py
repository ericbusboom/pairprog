from prompt_toolkit import Application
from prompt_toolkit import PromptSession
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.shortcuts import clear
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.formatted_text import to_formatted_text, HTML
from prompt_toolkit.key_binding.bindings.named_commands import accept_line
from prompt_toolkit.keys import Keys
from prompt_toolkit.data_structures import Point

style = Style.from_dict({
    'myinput': 'fg:#00ff00',  # Green in hex
    'reverse': 'fg:#0000ff',  # Blue in hex
    'charcount': 'fg:ansibrightgreen',  # Bright green using ANSI color name
})

# Key bindings for additional functionality
kb = KeyBindings()

@kb.add(Keys.ControlM)
def enter_(event):
    accept_line(event)

@kb.add('c-c')
@kb.add('c-q')
def exit_(event):
    " Press Ctrl-C or Ctrl-Q to exit. "
    event.app.exit()


history_b = Buffer()
history_b.text = to_formatted_text('History\n', 'class:myinput')
history_w = Window(content=BufferControl(buffer=history_b))
progress_w = Window(height=2, content=FormattedTextControl(
                    text=to_formatted_text('Progress', 'class:myinput')))
session = PromptSession()


def handle_submit(buff):
    text = buff.text

    #history_w.content.text += to_formatted_text(text+'\n', 'class:myinput')
    #history_w.content.text += to_formatted_text(text[::-1]+'\n', 'class:reverse')

    history_b.text += to_formatted_text(text+'\n', 'class:myinput')
    history_b.text += to_formatted_text(text[::-1]+'\n', 'class:reverse')


    #progress_w.content.text = [('class:charcount', f'Character count: {len(text)}')]

    buff.reset()

    return True


#input_buffer = Buffer(accept_handler=handle_submit)  # Editable buffer.
#input_window = Window(height=10, content=BufferControl(buffer=input_buffer))

input_window  = TextArea(
    name='input',
    height=10,
    prompt='>> ',
    multiline=True,
    wrap_lines=True,
    style='class:inputarea',
    accept_handler=handle_submit
)

root_container = HSplit([

    history_w,

    Window(height=1, char='-'),  # Horiz Line

    progress_w,

    Window(height=1, char='-'),  # Horiz Line

    input_window

])

layout = Layout(root_container)

# Initialize the application
app = Application(
    layout=layout,
    key_bindings=kb,
    style=style,
    full_screen=True,

)

app.layout.focus('input')

# Run the application
clear()
app.run()
