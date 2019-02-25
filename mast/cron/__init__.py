#!/usr/bin/env python
"""
_module_: `mast.cron`

This module does not provide any user-facing functionality. Interfacing
with this module should be done through the file `$MAST_HOME/etc/crontab`.

This module provides a `mastd_plugin` which will check for the existence
of `$MAST_HOME/etc/crontab`. If this file exists, it is scanned for
scheduled jobs. If scheduled jobs are present, they are checked to see
if they are due. If the scheduled job is due, then it is executed.

The file in `$MAST_HOME/etc/crontab` is expected to be a newline-seperated
list of [cron expressions](https://en.wikipedia.org/wiki/Cron#Format)
and will be evaluated every minute without the need to reload mastd.
"""

import os
import time
from mast.logging import make_logger, logged
import datetime
import calendar
import threading
import platform
import subprocess
from mast import __version__

try:
    mast_home = os.environ["MAST_HOME"]
except:
    mast_home = os.getcwd()

__all__ = ["CronExpression", "parse_atom", "DEFAULT_EPOCH", "SUBSTITUTIONS"]
__license__ = "Public Domain"

DAY_NAMES = zip(('sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'), xrange(7))
MINUTES = (0, 59)
HOURS = (0, 23)
DAYS_OF_MONTH = (1, 31)
MONTHS = (1, 12)
DAYS_OF_WEEK = (0, 6)
L_FIELDS = (DAYS_OF_WEEK, DAYS_OF_MONTH)
FIELD_RANGES = (MINUTES, HOURS, DAYS_OF_MONTH, MONTHS, DAYS_OF_WEEK)
MONTH_NAMES = zip(('jan', 'feb', 'mar', 'apr', 'may', 'jun',
                   'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), xrange(1, 13))
DEFAULT_EPOCH = (1970, 1, 1, 0, 0, 0)
SUBSTITUTIONS = {
    "@yearly": "0 0 1 1 *",
    "@anually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *"
}


class CronExpression(object):
    """
    _class_: `mast.cron.CronExpression(object)`

    This class represents a single cron expression. This should not
    need to be used directly, please use `$MAST_HOME/etc/crontab` to
    modify the behavior of this module.
    """
    def __init__(self, line, epoch=DEFAULT_EPOCH, epoch_utc_offset=0):
        """
        _method_: `mast.cron.CronExpression.__init__(self, line, epoch=DEFAULT_EPOCH, epoch_utc_offset=0)`

        Instantiates a CronExpression object with an optionally defined epoch.
        If the epoch is defined, the UTC offset can be specified one of two
        ways: as the sixth element in 'epoch' or supplied in epoch_utc_offset.
        The epoch should be defined down to the minute sorted by
        descending significance.
        """
        for key, value in SUBSTITUTIONS.items():
            if line.startswith(key):
                line = line.replace(key, value)
                break

        fields = line.split(None, 5)
        if len(fields) == 5:
            fields.append('')

        minutes, hours, dom, months, dow, self.comment = fields

        dow = dow.replace('7', '0').replace('?', '*')
        dom = dom.replace('?', '*')

        for monthstr, monthnum in MONTH_NAMES:
            months = months.lower().replace(monthstr, str(monthnum))

        for dowstr, downum in DAY_NAMES:
            dow = dow.lower().replace(dowstr, str(downum))

        self.string_tab = [minutes, hours, dom.upper(), months, dow.upper()]
        self.compute_numtab()
        if len(epoch) == 5:
            y, mo, d, h, m = epoch
            self.epoch = (y, mo, d, h, m, epoch_utc_offset)
        else:
            self.epoch = epoch

    def __str__(self):
        """
        _method_: `mast.cron.CronExpression.__str__(self)`

        Returns a `str` representation of this cron Expression.
        """
        base = self.__class__.__name__ + "(%s)"
        cron_line = self.string_tab + [str(self.comment)]
        if not self.comment:
            cron_line.pop()
        arguments = '"' + ' '.join(cron_line) + '"'
        if self.epoch != DEFAULT_EPOCH:
            return base % (arguments + ", epoch=" + repr(self.epoch))
        else:
            return base % arguments

    def __repr__(self):
        """
        _method_: `mast.cron.CronExpression.__repr__(self)`

        Returns a rerpresentation (same as `__str__`) of
        this cron expression.
        """
        return str(self)

    def compute_numtab(self):
        """
        _method_: `mast.cron.CronExpression.compute_numtab(self)`

        Recomputes the sets for the static ranges of the trigger time.

        This method should only be called by the user if the string_tab
        member is modified.
        """
        self.numerical_tab = []

        for field_str, span in zip(self.string_tab, FIELD_RANGES):
            split_field_str = field_str.split(',')
            if len(split_field_str) > 1 and "*" in split_field_str:
                raise ValueError("\"*\" must be alone in a field.")

            unified = set()
            for cron_atom in split_field_str:
                # parse_atom only handles static cases
                for special_char in ('%', '#', 'L', 'W'):
                    if special_char in cron_atom:
                        break
                else:
                    unified.update(parse_atom(cron_atom, span))

            self.numerical_tab.append(unified)

        if self.string_tab[2] == "*" and self.string_tab[4] != "*":
            self.numerical_tab[2] = set()

    def check_trigger(self, date_tuple, utc_offset=0):
        """
        _method_: `mast.cron.CronExpression.check_trigger(self, date_tuple, utc_offset=0)`

        Returns boolean indicating if the trigger is active at the given time.
        The date tuple should be in the local time. Unless periodicities are
        used, utc_offset does not need to be specified. If periodicities are
        used, specifically in the hour and minutes fields, it is crucial that
        the utc_offset is specified.
        """
        year, month, day, hour, mins = date_tuple
        given_date = datetime.date(year, month, day)
        zeroday = datetime.date(*self.epoch[:3])
        last_dom = calendar.monthrange(year, month)[-1]
        dom_matched = True

        # In calendar and datetime.date.weekday, Monday = 0
        given_dow = (datetime.date.weekday(given_date) + 1) % 7
        first_dow = (given_dow + 1 - day) % 7

        # Figure out how much time has passed from the epoch to the given date
        utc_diff = utc_offset - self.epoch[5]
        mod_delta_yrs = year - self.epoch[0]
        mod_delta_mon = month - self.epoch[1] + mod_delta_yrs * 12
        mod_delta_day = (given_date - zeroday).days
        mod_delta_hrs = hour - self.epoch[3] + mod_delta_day * 24 + utc_diff
        mod_delta_min = mins - self.epoch[4] + mod_delta_hrs * 60

        # Makes iterating through like components easier.
        quintuple = zip(
            (mins, hour, day, month, given_dow),
            self.numerical_tab,
            self.string_tab,
            (mod_delta_min, mod_delta_hrs, mod_delta_day, mod_delta_mon,
                mod_delta_day),
            FIELD_RANGES)

        for value, valid_values, field_str, delta_t, field_type in quintuple:
            # All valid, static values for the fields are stored in sets
            if value in valid_values:
                continue

            # The following for loop implements the logic for context
            # sensitive and epoch sensitive constraints. break statements,
            # which are executed when a match is found, lead to a continue
            # in the outer loop. If there are no matches found, the given date
            # does not match expression constraints, so the function returns
            # False as seen at the end of this for...else... construct.
            for cron_atom in field_str.split(','):
                if cron_atom[0] == '%':
                    if not(delta_t % int(cron_atom[1:])):
                        break

                elif field_type == DAYS_OF_WEEK and '#' in cron_atom:
                    D, N = int(cron_atom[0]), int(cron_atom[2])
                    # Computes Nth occurence of D day of the week
                    if (((D - first_dow) % 7) + 1 + 7 * (N - 1)) == day:
                        break

                elif field_type == DAYS_OF_MONTH and cron_atom[-1] == 'W':
                    target = min(int(cron_atom[:-1]), last_dom)
                    lands_on = (first_dow + target - 1) % 7
                    if lands_on == 0:
                        # Shift from Sun. to Mon. unless Mon. is next month
                        target += 1 if target < last_dom else -2
                    elif lands_on == 6:
                        # Shift from Sat. to Fri. unless Fri. in prior month
                        target += -1 if target > 1 else 2

                    # Break if the day is correct, and target is a weekday
                    if target == day and (first_dow + target - 7) % 7 > 1:
                        break

                elif field_type in L_FIELDS and cron_atom.endswith('L'):
                    # In dom field, L means the last day of the month
                    target = last_dom

                    if field_type == DAYS_OF_WEEK:
                        # Calculates the last occurence of given day of week
                        desired_dow = int(cron_atom[:-1])
                        target = (((desired_dow - first_dow) % 7) + 29)
                        target -= 7 if target > last_dom else 0

                    if target == day:
                        break
            else:
                # See 2010.11.15 of CHANGELOG
                if field_type == DAYS_OF_MONTH and self.string_tab[4] != '*':
                    dom_matched = False
                    continue
                elif field_type == DAYS_OF_WEEK and self.string_tab[2] != '*':
                    # If we got here, then days of months validated so it does
                    # not matter that days of the week failed.
                    return dom_matched

                # None of the expressions matched which means this field fails
                return False

        # Arriving at this point means the date landed within the constraints
        # of all fields; the associated trigger should be fired.
        return True


def parse_atom(parse, minmax):
    """
    _function_: `mast.cron.parse_atom(parse, minmax)`

    Returns a set containing valid values for a given cron-style range of
    numbers. The 'minmax' arguments is a two element iterable containing the
    inclusive upper and lower limits of the expression.

    Examples:

        :::python
        >>> parse_atom("1-5",(0,6))
        set([1, 2, 3, 4, 5])

        >>> parse_atom("*/6",(0,23))
        set([0, 6, 12, 18])

        >>> parse_atom("18-6/4",(0,23))
        set([18, 22, 0, 4])

        >>> parse_atom("*/9",(0,23))
        set([0, 9, 18])
    """
    parse = parse.strip()
    increment = 1
    if parse == '*':
        return set(xrange(minmax[0], minmax[1] + 1))
    elif parse.isdigit():
        # A single number still needs to be returned as a set
        value = int(parse)
        if value >= minmax[0] and value <= minmax[1]:
            return set((value,))
        else:
            raise ValueError("Invalid bounds: \"%s\"" % parse)
    elif '-' in parse or '/' in parse:
        divide = parse.split('/')
        subrange = divide[0]

        if len(divide) == 2:
            # Example: 1-3/5 or */7 increment should be 5 and 7 respectively
            increment = int(divide[1])

        if '-' in subrange:
            # Example: a-b
            prefix, suffix = [int(n) for n in subrange.split('-')]
            if prefix < minmax[0] or suffix > minmax[1]:
                raise ValueError("Invalid bounds: \"%s\"" % parse)
        elif subrange == '*':
            # Include all values with the given range
            prefix, suffix = minmax
        else:
            raise ValueError("Unrecognized symbol: \"%s\"" % subrange)

        if prefix < suffix:
            # Example: 7-10
            return set(xrange(prefix, suffix + 1, increment))
        else:
            # Example: 12-4/2; (12, 12 + n, ..., 12 + m*n) U (n_0, ..., 4)
            noskips = list(xrange(prefix, minmax[1] + 1))
            noskips += list(xrange(minmax[0], suffix + 1))
            return set(noskips[::increment])


class Plugin(threading.Thread):
    """
    _class_: `mast.cron.Plugin(threading.Thread)`

    This class is a mastd plugin, which is a subclass of
    `threading.Thread`. This plugin will read `$MAST_HOME/etc/crontab`
    each minute and parse each line as a cron-style task. If the task
    is due, it will be executed.
    """
    def __init__(self, crontab=os.path.join(mast_home, "etc", "crontab")):
        """
        _method_: `mast.cron.Plugin.__init__(self, crontab=os.path.join(mast_home, "etc", "crontab"))`

        Plugin is a subclass of thread which reads crontab once
        every minute to see if any tasks defined in crontab are due.
        If a task is due it will be executed, if not it will be logged
        that it is not due.

        To stop this thread call the stop() method of your instance."""
        super(Plugin, self).__init__()
        self.daemon = True
        self.crontab = crontab
        self._stop = False

    @logged("mast.cron")
    def stop(self):
        """
        _method_: `mast.cron.Plugin.stop(self)`

        Ends this Scheduler Thread
        """
        self._stop = True

    @logged("mast.cron")
    def run(self):
        """
        _method_: `mast.cron.Plugin.run(self)`

        Overloaded run method. This thread will check crontab
        every minute for tasks which are due to run. If a task
        is found to be due, execute it, otherwise log a message
        and continue
        """
        logger = make_logger("mast.cron")
        while not self._stop:
            logger.info("Checking for tasks which are sceduled to run.")
            if os.path.exists(self.crontab):
                with open(self.crontab, "r") as fin:
                    for line in fin.readlines():
                        logger.info(
                            "Found task "
                            "'{}'...checking if task is due...".format(
                                line.strip()))
                        job = CronExpression(line.strip())
                        try:
                            if job.check_trigger(time.gmtime(time.time())[:5]):
                                if "Windows" in platform.system():
                                    si = subprocess.STARTUPINFO()
                                    si.dwFlags |= \
                                        subprocess.STARTF_USESHOWWINDOW
                                    out = subprocess.check_output(
                                        job.comment.strip(),
                                        shell=True,
                                        stdin=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        startupinfo=si)
                                elif "Linux" in platform.system():
                                    out = subprocess.check_output(
                                        job.comment.strip(),
                                        shell=True,
                                        stderr=subprocess.STDOUT)
                                if out:
                                    logger.info("Task '{}' completed. Output: '{}'".format(
                                        line,
                                        out.replace(
                                            "\n", "").replace(
                                                "\r", "")))
                            else:
                                logger.info(
                                    "Task '{}' not scheduled to run.".format(
                                        job.comment))
                        except Exception:
                            logger.exception(
                                "Sorry an unhandled exception occurred. "
                                "Attempting to continue...")
                            pass
            else:
                logger.info(
                    "Crontab file does not exist, to enable this"
                    "plugin please create the file {}".format(self.crontab))
            # Check every minute, otherwise you hit an interesting bug.
            # every time it checks for pending jobs if it's within
            # the minute, The scheduler doesn't take into account if
            # the job already ran in the current minute. Rather than
            # tackle this bug and make this more complicated than it
            # has to be, I figured just supporting every minute was
            # good enough.
            time.sleep(60)
