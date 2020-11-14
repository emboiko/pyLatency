from tkinter import (
    Tk,
    Frame, 
    Canvas, 
    Entry, 
    Button, 
    Label, 
    Scale,
    Listbox,
    PanedWindow
)
from sys import platform
from subprocess import run
from re import findall
from time import sleep
from threading import Thread
from os.path import dirname


class PyLatency:
    """Ping tool visualization"""

    def __init__(self, root):
        """Setup window geometry & widgets + layout"""

        self.master = root
        self.master.title("pyLatency")
        self.master.geometry("500x300")
        self.master.minsize(width=250, height=200)
        self.master.update()
        self.master.iconbitmap(f"{dirname(__file__)}/icon.ico")

        #misc:
        self.running = False
        self.hostname = None
        self.RECT_SCALE_FACTOR = 2 #todo

        # Widgets:
        self.frame = Frame(self.master)

        self.lbl_entry = Label(self.frame, text="Host:")
        self.lbl_status = Label(self.frame, text="Ready")
        self.lbl_error = Label(self.frame, fg="red")
        self.entry = Entry(self.frame)

        self.btn_start = Button(
            self.frame, 
            text="Start", 
            command=self.start
            )

        self.btn_stop = Button(
            self.frame, 
            text="Stop",
            command=self.stop
        )

        self.delay_scale = Scale(
            self.frame, 
            label="Interval (ms)", 
            orient="horizontal",
            from_=100,
            to=5000,
            resolution=100,
        )
        self.delay_scale.set(1000)

        self.paneview = PanedWindow(
            self.master, 
            sashwidth=5,
            bg="#cccccc"
        )
        self.left_pane = PanedWindow(self.paneview)
        self.right_pane = PanedWindow(self.paneview)
        self.paneview.add(self.left_pane)
        self.paneview.add(self.right_pane)

        self.canvas = Canvas(self.left_pane, bg="#FFFFFF")
        self.ping_list = Listbox(
            self.right_pane, 
            highlightthickness=0,
            font=14,
            selectmode="disabled")

        self.left_pane.add(self.canvas)
        self.right_pane.add(self.ping_list)

        # Layout:
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(1, weight=1)

        self.frame.columnconfigure(1, weight=1)

        self.frame.grid(row=0, column=0, sticky="nsew")

        self.lbl_entry.grid(row=0, column=0)
        self.lbl_status.grid(row=1, column=0, columnspan=5)
        self.lbl_error.grid(row=2, column=0, columnspan=5)
        self.entry.grid(row=0, column=1, sticky="ew")
        self.btn_start.grid(row=0, column=2)
        self.btn_stop.grid(row=0, column=3)
        self.delay_scale.grid(row=0, column=4, rowspan=2)

        self.paneview.grid(row=1, column=0, sticky="nsew")

        self.paneview.paneconfigure(
            self.left_pane,
            width=(self.master.winfo_width() - self.delay_scale.winfo_reqwidth()),
        )

        #Bindings:
        self.master.bind("<Return>", self.start)
        self.master.bind("<Escape>", self.stop)
        self.master.bind("<Control-w>", lambda event: self.master.destroy())
        self.master.bind(
            "<Up>", 
            lambda event: self.delay_scale.set(
                self.delay_scale.get() + 100
            )
        )
        self.master.bind(
            "<Down>", 
            lambda event: self.delay_scale.set(
                self.delay_scale.get() - 100
            )
        )


    def start(self, event=None):
        """
            Reset the GUI, create & start a thread so we don't block
            the mainloop during each poll. 
        """

        if not self.running:
            self.hostname = self.entry.get()
            if self.hostname:
                self.ping_list.delete(0,"end")
                self.canvas.delete("all")
                self.lbl_status.config(text="Running", fg="green")
                self.lbl_error.config(text="")
                self.running = True
                self.thread = Thread(target=self.run, daemon=True)
                self.thread.start()
            else:
                self.lbl_error.config(text="Missing Hostname")


    def run(self):
        """
            Continuously shell out to ping, get an integer result, 
            update the GUI, and wait. 
        """

        while self.running:
            latency = self.ping(self.hostname)
            if latency is None:
                self.stop()
                self.lbl_error.config(text="Unable to ping host")
            self.update_gui(latency)
            sleep(self.delay_scale.get() / 1000)


    def update_gui(self, latency):
        """
        Update the listbox, shift all existing rectangles, draw the latest
        result from self.ping(), cleanup unused rectangles, update the mainloop
        """

        self.ping_list.insert(0, str(latency) + "ms")

        self.canvas.move("rect",10,0)
        self.canvas.create_rectangle(
            0,
            0,
            10,
            int(latency * self.RECT_SCALE_FACTOR), 
            fill="#333333",
            tags="rect",
        )

        self.cleanup_rects()
        self.master.update()


    def cleanup_rects(self):
        """Delete rectangles that are outside the bbox of the canvas"""

        for rect in self.canvas.find_withtag("rect"):
            if self.canvas.coords(rect)[0] > self.canvas.winfo_width():
                self.canvas.delete(rect)


    def stop(self, event=None):
        """Satisfy the condition in which self.thread exits"""

        if self.running:
            self.running = False
            self.lbl_status.config(text="Stopped", fg="red")


    @staticmethod
    def ping(url):
        """
        Shell out to ping and return an integer result.
        Returns None if ping fails for any reason: timeout, bad hostname, etc.
        """

        flag = '-n' if platform == 'win32' else '-c'
        result = run(['ping', flag, '1', url], capture_output=True)
        output = result.stdout.decode("utf-8")
        try:
            duration = findall("\d+ms", output)[0]
            return int(duration[:-2])
        except IndexError:
            return None


def main():
    """Initialize Tk root window and subclass it with the GUI"""

    root = Tk()
    PyLatency(root)
    root.mainloop()


if __name__ == "__main__":
    main()
