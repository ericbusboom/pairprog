import curses
import curses.textpad
import os


def input_validator(ch):
    """Custom validator for text input. Ends on two Enter presses."""
    return ch


def main(stdscr):
    # Set up curses environment
    curses.curs_set(1)  # Show cursor
    stdscr.keypad(True)  # Enable special keys to be handled as single values

    # Calculate window sizes
    max_y, max_x = stdscr.getmaxyx()
    input_height = 10
    count_height = 3
    file_display_height = max_y - input_height - count_height

    # Create windows for each pane
    file_window = curses.newwin(file_display_height, max_x, 0, 0)
    count_window = curses.newwin(count_height, max_x, file_display_height, 0)
    input_window = curses.newwin(input_height, max_x, file_display_height + count_height, 0)

    file_window.scrollok(True)
    file_window.idlok(True)

    input_window.scrollok(True)

    while True:
        # Clear windows
        file_window.clear()
        count_window.clear()
        input_window.clear()

        input_window.addstr("Enter file path(s), press Ctrl-G to end:\n")
        editwin_height = input_height - 3
        editwin_width = max_x - 4
        editwin_y = file_display_height + count_height + 1
        editwin_x = 2

        # Ensure the edit window fits within the input_window
        editwin_height = min(editwin_height, max_y - editwin_y - 1)
        editwin_width = min(editwin_width, max_x - editwin_x - 1)

        editwin = curses.newwin(editwin_height, editwin_width, editwin_y, editwin_x)
        box = curses.textpad.Textbox(editwin)

        # Ensure rectangle fits within the bounds of input_window
        rectangle_ul_y = editwin_y
        rectangle_ul_x = editwin_x
        rectangle_lr_y = editwin_y + editwin_height
        rectangle_lr_x = editwin_x + editwin_width

        #curses.textpad.rectangle(editwin, rectangle_ul_y, rectangle_ul_x, rectangle_lr_y, rectangle_lr_x)
        curses.textpad.rectangle(count_window, 0, 0, 2, max_x-2)
        #editwin.move(0,0)
        input_window.refresh()

        # Let the user edit until Ctrl-G is pressed

        box.edit(input_validator)  # Use the custom validator
        input_text = box.gather()

        # Process each file path
        file_content = ""
        char_count = 0
        for file_path in input_text.splitlines():
            if file_path.strip():
                if os.path.exists(file_path.strip()):
                    with open(file_path.strip(), 'r') as file:
                        content = file.read()
                        file_content += content + '\n'
                        char_count += len(content)
                else:
                    file_window.addstr(f"\nFile not found: {file_path.strip()}")

        file_window.addstr(file_content)
        count_window.addstr(1,1,f"Character count: {char_count}")
        file_window.refresh()
        count_window.refresh()

        # Handle scrolling
        while True:
            key = file_window.getch()
            if key == curses.KEY_NPAGE:  # Page Down
                file_window.scroll(file_display_height)
            elif key == curses.KEY_PPAGE:  # Page Up
                file_window.scroll(-file_display_height)
            elif key == curses.KEY_HOME:  # Home
                file_window.move(0, 0)
            elif key == curses.KEY_END:  # End
                file_window.move(file_window.getmaxyx()[0] - 1, 0)
            elif key in [10, 13]:  # Enter key or Ctrl-G (BEL)
                break

            file_window.refresh()

        # Reset cursor to input window
        curses.setsyx(input_height + count_height+1, 0)
        input_window.clear()
        input_window.refresh()


if __name__ == "__main__":
    curses.wrapper(main)
