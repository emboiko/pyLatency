from tkinter import (
    Tk,
    Frame, 
    Canvas, 
    Entry, 
    Button, 
    Label, 
    Scale,
    Listbox,
    Scrollbar,
    PanedWindow,
    Checkbutton,
    BooleanVar
)
from os import mkdir, getenv
from os.path import exists
from sys import platform
from datetime import datetime
from time import sleep
from timeit import default_timer
from json import loads, dumps
from re import findall
from collections import deque
from subprocess import run, DETACHED_PROCESS
from threading import Thread
from functools import wraps


class PyLatency:
    """Ping tool visualization with tkinter"""

    def __init__(self, root):
        """Setup window geometry & widgets + layout, init counters"""

        self.master = root
        self.master.title("pyLatency")
        self.appdata_dir = getenv("APPDATA") + "/pyLatency"
        self.options_path = self.appdata_dir + "/options.json"
        self.log_dir = self.appdata_dir + "/logs"
        self.logfile = None

        self.options_logging = BooleanVar()
        self.options_geometry = ""

        self.options = self.init_options()
        if self.options:
            self.options_geometry = self.options["geometry"]
            self.options_logging.set(self.options["logging"])

        if self.options_geometry:
            self.master.geometry(self.options_geometry)
        else:
            self.master.geometry("400x200")

        self.master.minsize(width=400, height=200)
        self.master.update()

        self.running = False
        self.hostname = None
        self.RECT_SCALE_FACTOR = 2
        self.TIMEOUT = 5000
        self.minimum = self.TIMEOUT
        self.maximum = 0
        self.average = 0
        self.SAMPLE_SIZE = 1000
        self.sample = deque(maxlen=self.SAMPLE_SIZE)
        self.pcount = 0
        self.max_bar = None
        self.min_bar = None

        # Widgets:
        self.frame = Frame(self.master)

        self.lbl_entry = Label(self.frame, text="Host:")
        self.lbl_status_1 = Label(self.frame, text="Ready")
        self.lbl_status_2 = Label(self.frame, fg="red")
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

        self.chk_log = Checkbutton(
            self.frame, 
            text="Enable log", 
            variable=self.options_logging
        )

        self.delay_scale = Scale(
            self.frame, 
            label="Interval (ms)", 
            orient="horizontal",
            from_=100,
            to=self.TIMEOUT,
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

        self.canvas_scroll_y = Scrollbar(self.left_pane)
        self.canvas = Canvas(
            self.left_pane,
            bg="#FFFFFF",
            yscrollcommand=self.canvas_scroll_y.set
        )
        self.canvas_scroll_y.config(command=self.canvas.yview)
        self.left_pane.add(self.canvas_scroll_y)

        self.ping_list_scroll = Scrollbar(self.master)
        self.ping_list = Listbox(
            self.right_pane, 
            highlightthickness=0,
            font=14,
            selectmode="disabled",
            yscrollcommand=self.ping_list_scroll.set)
        self.ping_list_scroll.config(command=self.ping_list.yview)
        self.right_pane.add(self.ping_list_scroll)

        self.left_pane.add(self.canvas)
        self.right_pane.add(self.ping_list)

        # Layout:
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(1, weight=1)

        self.frame.columnconfigure(1, weight=1)

        self.frame.grid(row=0, column=0, sticky="nsew")

        self.lbl_entry.grid(row=0, column=0)
        self.lbl_status_1.grid(row=1, column=0, columnspan=4)
        self.lbl_status_2.grid(row=2, column=0, columnspan=4)
        self.entry.grid(row=0, column=1, sticky="ew")
        self.btn_start.grid(row=0, column=2)
        self.btn_stop.grid(row=0, column=3)
        self.chk_log.grid(row=1, column=2, columnspan=2)
        self.delay_scale.grid(row=0, column=4, rowspan=2)

        # self.canvas_scroll_y.grid(row=1, column=2, sticky="ns")
        self.paneview.grid(row=1, column=0, sticky="nsew")
        # self.ping_list_scroll.grid(row=1, column=1, sticky="ns")

        self.paneview.paneconfigure(
            self.left_pane,
            width=(self.master.winfo_width() - self.delay_scale.winfo_reqwidth()),
        )

        #Bindings:
        self.canvas.bind("<MouseWheel>", self.scroll_canvas)

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

        self.master.protocol("WM_DELETE_WINDOW", self.master_close)


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
                self.lbl_status_1.config(text="Running", fg="green")
                self.lbl_status_2.config(text="")

                self.sample.clear()

                (self.minimum,
                self.maximum, 
                self.average,
                self.pcount) = self.TIMEOUT, 0, 0, 0

                self.running = True
                self.thread = Thread(target=self.run, daemon=True)
                self.thread.start()
            else:
                self.lbl_status_2.config(text="Missing Hostname")


    def logged(fn):
        """
            decorates self.run(), create a log directory if one doesn't
            exist, create a filename with a date & timestamp, call self.run()
            with logging enabled or disabled
        """

        @wraps(fn)
        def inner(self):
            if self.options_logging.get():
                if not exists(self.log_dir):
                    mkdir(self.log_dir)

                timestamp = datetime.now()
                fname = timestamp.strftime("%a %b %d @ %H-%M-%S")

                with open(self.log_dir + f"/{fname}.txt", "w+") as self.logfile:
                    self.logfile.write(f"pyLatency {fname}\n")
                    self.logfile.write(f"Host: {self.hostname}\n")
                    self.logfile.write("-" * 40 + "\n")
                    start = default_timer()
                    fn(self)
                    end = default_timer()
                    elapsed = end - start
                    self.logfile.write("-" * 40 + "\n")
                    self.logfile.write(
                        f"Logged {self.pcount} pings over {int(elapsed)} seconds"
                    )
            else:
                fn(self)

        return inner


    @logged
    def run(self):
        """
            Continuously shell out to ping, get an integer result, 
            update the GUI, and wait. 
        """

        while self.running:
            latency = self.ping(self.hostname)
            self.pcount += 1

            if latency is None:
                self.stop()
                self.lbl_status_2.config(text="Unable to ping host")
                return
            if latency > self.maximum:
                self.maximum = latency
            if latency < self.minimum:
                self.minimum = latency
            
            self.sample.append(latency)
            self.average = sum(self.sample) / len(self.sample)

            if self.logfile:
                self.logfile.write(str(latency)+"\n")

            self.update_gui(latency)
            sleep(self.delay_scale.get() / 1000)


    def update_gui(self, latency):
        """
            Update the listbox, shift all existing rectangles, draw the latest
            result from self.ping(), cleanup unused rectangles, update the mainloop
        """

        if self.ping_list.size() >= self.SAMPLE_SIZE:
            self.ping_list.delete(self.SAMPLE_SIZE - 1, "end")

        self.ping_list.insert(0, str(latency) + "ms")

        self.canvas.move("rect",10,0)
        self.canvas.create_rectangle(
            0,
            0,
            10,
            int(latency * self.RECT_SCALE_FACTOR), 
            fill="#333333",
            tags="rect",
            width=0
        )

        self.canvas.delete(self.max_bar)
        self.max_bar = self.canvas.create_line(
            0,
            self.maximum * self.RECT_SCALE_FACTOR,
            self.canvas.winfo_width(),
            self.maximum * self.RECT_SCALE_FACTOR,
            fill="red",
        )
        self.canvas.delete(self.min_bar)
        self.min_bar = self.canvas.create_line(
            0,
            self.minimum * self.RECT_SCALE_FACTOR,
            self.canvas.winfo_width(),
            self.minimum * self.RECT_SCALE_FACTOR,
            fill="green",
        )

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.lbl_status_2.config(
            fg="#000000", 
            text=f"Min: {self.minimum} "
            f"Max: {self.maximum} "
            f"Avg: {round(self.average,2):.2f}"
        )

        self.cleanup_rects()
        self.master.update()

    
    def scroll_canvas(self, event):
        print(event.delta)

        count = None
        if event.num == 5 or event.delta == -120:
            count = 1
        if event.num == 4 or event.delta == 120:
            count = -1

        self.canvas.yview_scroll(count, "units")


    def cleanup_rects(self):
        """Delete rectangles that are outside the bbox of the canvas"""

        for rect in self.canvas.find_withtag("rect"):
            if self.canvas.coords(rect)[0] > self.canvas.winfo_width():
                self.canvas.delete(rect)


    def stop(self, event=None):
        """Satisfy the condition in which self.thread exits"""

        if self.running:
            self.running = False
            self.lbl_status_1.config(text="Stopped", fg="red")


    def master_close(self, event=None):
        """Writes window geometry/options to the disk."""

        options=dumps({
            "geometry" : self.master.geometry(),
            "logging" : self.options_logging.get()
        })

        if not exists(self.appdata_dir):
            mkdir(self.appdata_dir)

        with open(self.options_path, "w+") as options_file:
            options_file.write(options)
        
        self.master.destroy()


    def init_options(self):
        """Called on startup, loads, parses, and returns options from json."""

        if exists(self.options_path):
            with open(self.options_path, "r") as options_file:
                options_json=options_file.read()

            return loads(options_json)
        else:
            return None


    @staticmethod
    def ping(url):
        """
            Shell out to ping and return an integer result.
            Returns None if ping fails for any reason: timeout, bad hostname, etc.
        """

        flag = "-n" if platform == "win32" else "-c"
        result = run(
            ["ping", flag, "1", "-w", "5000", url],
            capture_output=True, 
            creationflags=DETACHED_PROCESS
        )
        output = result.stdout.decode("utf-8")
        try:
            duration = findall("\\d+ms", output)[0]
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
