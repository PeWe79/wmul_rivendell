"""
@Author = 'Michael Stanley'

Command-Line-Interface for the various modules in this package.

============ Change Log ============
2025-Jun-18 = Add convert-to-excel and convert-to-csv.
              Refactor filter-cart-report.

2025-Jan-29 = Add option to database_statistics for write_full_statistics option on DatabaseStatistics.

2025-Jan-23 = Add options to database_statistics for smallest_stdev, minimum_population, upper and lower bound 
              multiples. 

2025-Jan-03 = Add database_statistics option.
              Fix type in help text of filter_cart_report.

2023-May-25 = Refactor filter_cart_report to reflect that the loading of the
                cart data from a file has been refactored into LoadCartDataDump.

2023-Jan-20 = Change license from GPLv2 to GPLv3.
              Back-insert items into change log.
              Update description.

2023-Jan-19 = Add --fix_header to filter_cart_report. 
              Change the cli options to use the versions of RequiredIf and 
                MXWith now in wmul_click_utils.

2022-May-16 = Fix cli help for load_current_log_line.

2022-May-06 = Update documentation.

2020-Oct-15 = Add current version number to logging.
              Add ability for RivendellAudioImporter to tell rdimport where to
                log.
              Log final crashes of RivendellAudioImporter.

2020-Jun-26 = Created.

============ License ============
Copyright (C) 2020, 2022-2023, 2025 Michael Stanley

This file is part of wmul_rivendell.

wmul_rivendell is free software: you can redistribute it and/or modify it 
under the terms of the GNU General Public License as published by the Free 
Software Foundation, either version 3 of the License, or (at your option) any 
later version.

wmul_rivendell is distributed in the hope that it will be useful, but WITHOUT 
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with 
wmul_rivendell. If not, see <https://www.gnu.org/licenses/>. 
"""
import click
import datetime

from pathlib import Path
from wmul_rivendell import __version__
from wmul_rivendell.DatabaseStatistics import DatabaseStatistics, StatisticsLimits
from wmul_rivendell.FilterCartReportForMusicScheduler import ConvertDatabaseToCSV, ConvertDatabaseToExcel
from wmul_rivendell.LoadCartDataDump import LoadCartDataDump
from wmul_rivendell.LoadCurrentLogLine import LoadCurrentLogLineArguments, run_script as load_current_log_lines
from wmul_rivendell.RivendellAudioImporter import \
    ImportRivendellFileWithFileSystemMetadataArguments, run_script as import_rivendell_file
from wmul_click_utils import RequiredIf, MXWith

import wmul_emailer
import wmul_logger


_logger = wmul_logger.get_logger()


@click.group()
@click.version_option()
@click.option('--log_name', type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True), default=None,
              required=False, help="The path to the log file.")
@click.option('--log_level', type=click.IntRange(10, 50, clamp=True), required=False, default=30,
              help="The log level: 10: Debug, 20: Info, 30: Warning, 40: Error, 50: Critical. "
                   "Intermediate values (E.G. 32) are permitted, but will essentially be rounded up (E.G. Entering 32 "
                   "is the same as entering 40. Logging messages lower than the log level will not be written to the "
                   "log. E.G. If 30 is input, then all Debug, Info, and Verbose messages will be silenced.")
def wmul_rivendell_cli(log_name, log_level):
    if log_name:
        global _logger
        _logger = wmul_logger.setup_logger(file_name=log_name, log_level=log_level)
        _logger.warning(f"Version: {__version__}")
        _logger.warning("In command_line_interface")


@wmul_rivendell_cli.command()
@click.argument('rivendell_cart_filename', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
                nargs=1)
@click.argument('output_filename', type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True),
                nargs=1)
@click.option('--include_all_cuts', is_flag=True,
              help="Whether to use every cut in the cart when making the calculations. If this is set, every cut from "
              "each cart will be used in the calculations. If it is not set, only the lowest numbered cut will be " 
              "used.")
@click.option('--excluded_groups_file_name', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
              help="File path to a text file containing a list of groups to be exluded. The file should have one "
              "group name on each line. A group name may be present in this file but not in the cart data dump.")
@click.option('--smallest_stdev', type=int, default=15, help="The smallest standard deviation (in seconds) permitted for "
              "calculating outliers, and upper and lower bounds for excluding songs. If the group population standard "
              "deviation is less than this number, then no outliers will be excluded. If the population (excluding "
              "outliers) standard deviation is less than this number, then no lower and upper boundes will be "
              "calculated. This limit helps avoid unwanted behaviour when a group is mostly the same length. E.G. a "
              "group containing only 30 second spots.")
@click.option("--minimum_population", type=int, default=4, help="The smallest population for calculating outliers. If "
              "the population of the group is smaller than or equal to this number, then outliers will not be " 
              "calculated and excluded.")
@click.option("--lower_bound_multiple", type=float, default=1.5, help="The standard deviation will be multiplied by " 
              "this number and subtracted from the mean to generate the lower bound.")
@click.option("--upper_bound_multiple", type=float, default=3.0, help="The standard deviation will be multiplied by " 
              "this number and added to the mean to generate the upper bound.")
@click.option("--write_limits", is_flag=True, help="Whether to write the statistics limits (smallest_stdev, "
              "minimum_population, lower_bound_multiple, and upper_bound_multiple) to the file.")
@click.option("--write_full_statistics", is_flag=True, help="If true, the full set of statistics will be written. " 
              "If false, only the summary statistics (Number of Songs, Lower Bound, Upper Bound) will be written.")
def database_statistics(rivendell_cart_filename, output_filename, include_all_cuts, excluded_groups_file_name, 
                        smallest_stdev, minimum_population, lower_bound_multiple, upper_bound_multiple, write_limits,
                        write_full_statistics):
    _logger.debug(f"With {locals()}")

    stats_limits = StatisticsLimits(
        smallest_stdev=smallest_stdev,
        minimum_population_for_outliers=minimum_population,
        lower_bound_multiple=lower_bound_multiple,
        upper_bound_multiple=upper_bound_multiple
    )

    excluded_groups = get_items_from_file(file_name=excluded_groups_file_name)
    output_filename = Path(output_filename)

    lcdd = LoadCartDataDump(
        rivendell_cart_data_filename=rivendell_cart_filename,
        include_all_cuts=include_all_cuts,
        include_macros=False,
        excluded_group_list=excluded_groups
    )

    rivendell_carts = lcdd.load_carts()

    x = DatabaseStatistics(
        rivendell_carts=rivendell_carts,
        output_filename=output_filename,
        stats_limits=stats_limits,
        write_limits=write_limits,
        write_full_statistics=write_full_statistics
    )
    x.run_script()


@wmul_rivendell_cli.command()
@click.argument('rivendell_cart_filename', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
                nargs=1)
@click.argument('output_filename', type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True),
                nargs=1)
@click.option('--desired_fields_filename', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
                help="File path to a text file containing a list of desired fields. The file should have one desired "
                "field per line.")
@click.option('--include_macros', is_flag=True, help="Include macro carts in the output file.")
@click.option('--include_all_cuts', is_flag=True,
              help="Include all the individual cuts in the output file. If this is left unset, then the output file "
                   "will only include the lowest numbered cut in each cart.")
@click.option('--excluded_groups_file_name', 
              type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
              help="File path to a text file containing a list of groups to be exluded. The file should have one "
              "group name on each line. A group name may be present in this file but not in the cart data dump.")
@click.option('--use_trailing_comma', is_flag=True,
              help="Include a comma at the end of each line. Required by some scheduling software, such as Natural "
                   "Music, to see the final field.")
def convert_to_csv(rivendell_cart_filename, output_filename, desired_fields_filename, include_macros,
                       include_all_cuts, excluded_groups_file_name, use_trailing_comma):
    _logger.debug(f"With {locals()}")
    converter = ConvertDatabaseToCSV.get_factory(use_trailing_comma=use_trailing_comma)
    convert_cart_database(
        rivendell_cart_filename=rivendell_cart_filename,
        output_filename=output_filename,
        desired_fields_filename=desired_fields_filename,
        include_macros=include_macros,
        include_all_cuts=include_all_cuts,
        excluded_groups_file_name=excluded_groups_file_name,
        converter=converter
    )


@wmul_rivendell_cli.command()
@click.argument('rivendell_cart_filename', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
                nargs=1)
@click.argument('output_filename', type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True),
                nargs=1)
@click.option('--desired_fields_filename', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
                help="File path to a text file containing a list of desired fields. The file should have one desired "
                "field per line.")
@click.option('--include_macros', is_flag=True, help="Include macro carts in the output file.")
@click.option('--include_all_cuts', is_flag=True,
              help="Whether to use every cut in the cart when making the calculations. If this is set, every cut from "
              "each cart will be used in the calculations. If it is not set, only the lowest numbered cut will be " 
              "used.")
@click.option('--excluded_groups_file_name', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
              help="File path to a text file containing a list of groups to be exluded. The file should have one "
              "group name on each line. A group name may be present in this file but not in the cart data dump.")
def convert_to_excel(rivendell_cart_filename, output_filename, desired_fields_filename, include_macros, include_all_cuts, excluded_groups_file_name):
    _logger.debug(f"With {locals()}")
    convert_cart_database(
        rivendell_cart_filename=rivendell_cart_filename,
        output_filename=output_filename,
        desired_fields_filename=desired_fields_filename,
        include_macros=include_macros,
        include_all_cuts=include_all_cuts,
        excluded_groups_file_name=excluded_groups_file_name,
        converter=ConvertDatabaseToExcel
    )


@wmul_rivendell_cli.command()
@click.argument('rivendell_cart_filename', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
                nargs=1)
@click.argument('output_filename', type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True),
                nargs=1)
@click.argument('desired_fields_filename', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
                nargs=1)
@click.option('--include_macros', is_flag=True, help="Include macro carts in the output file.")
@click.option('--include_all_cuts', is_flag=True,
              help="Include all the individual cuts in the output file. If this is left unset, then the output file "
                   "will only include the lowest numbered cut in each cart.")
@click.option('--excluded_groups_file_name', 
              type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
              help="File path to a text file containing a list of groups to be exluded. The file should have one "
              "group name on each line. A group name may be present in this file but not in the cart data dump.")
@click.option('--use_trailing_comma', is_flag=True,
              help="Include a comma at the end of each line. Required by some scheduling software, such as Natural "
                   "Music, to see the final field.")
def filter_cart_report(rivendell_cart_filename, output_filename, desired_fields_filename, include_macros,
                       include_all_cuts, excluded_groups_file_name, use_trailing_comma):
    _logger.debug(f"With {locals()}")
    converter = ConvertDatabaseToCSV.get_factory(use_trailing_comma=use_trailing_comma)
    convert_cart_database(
        rivendell_cart_filename=rivendell_cart_filename,
        output_filename=output_filename,
        desired_fields_filename=desired_fields_filename,
        include_macros=include_macros,
        include_all_cuts=include_all_cuts,
        excluded_groups_file_name=excluded_groups_file_name,
        converter=converter
    )


@wmul_rivendell_cli.command()
@click.argument('log_name_format', type=str, nargs=1)
@click.argument('rivendell_host', type=str, nargs=1)
@click.option('--sql_host', type=str, nargs=1, default="localhost",
              help="The host name to the SQL database. Usually localhost. Default: localhost.")
@click.option('--sql_user', type=str, nargs=1, default="rduser",
              help="The username for the SQL database. Usually rduser. Default: rduser.")
@click.option('--sql_pass', type=str, nargs=1, default="letmein",
              help="The password for the SQL database. Usually letmein. Default: letmein.")
@click.option('--sql_database_name', type=str, nargs=1, default="Rivendell",
              help="The Database name of the SQL database. Usually Rivendell. Default: Rivendell.")
@click.option('--use_date', type=click.DateTime(formats=["%Y-%m-%d", "%y-%m-%d"]), nargs=1,
              help="The date of the log to be loaded. Format is YY-MM-DD or YYYY-MM-DD. If this option is omitted, "
                   "the system date of the system running the script will be used.")
@click.option('--use_time',
              type=click.DateTime(formats=["%I:%M:%S %p", "%I:%M %p", "%I %p", "%H:%M:%S", "%H:%M", "%H"]),
              nargs=1, help="The time of the log line to be loaded. The script will find the line closest to, but "
                            "before that time. Valid formats are HH:MM:SS AM, HH:MM AM, HH AM, HH:MM:SS, HH:MM, and HH."
                            "If AM/PM are present, HH will be 12-hour. If AM/PM are absent, HH will be 24-hour. IF MM "
                            "and/or SS are omitted, they will be set to 00. If this option is omitted,"
                            "the system time of the system running the script will be used.")
@click.option('--dry_run', is_flag=True,
              help="For testing purposes. Prints out the log line that is selected, but does not load it.")
@click.option('--start_immediately', is_flag=True,
              help="Starts the selected log line immediately. If not set, the selected log line will be 'made next'.")
@click.option('--days_back', type=int, nargs=1, default=7,
              help="Maximum number of days back in time to go. If a log is not available for the given day, the script"
                   " will try to load the previous day's log. It will keep going back in time up to and including "
                   "this many days. This option is for cases where it is preferred to load and replay an old log "
                   "rather than no log. If no logs can be found for those dates, it will try to load the default log, "
                   "if provided. Set this value to 0 to not attempt previous days' logs. Defaults to 7.")
@click.option('--default_log', type=str, nargs=1,
              help="The full name of the last-ditch log to try to load if day based logs fail.")
@click.option('--log_machine', type=int, nargs=1, default=1,
              help="The log machine on which to load the playlist. Defaults to 1 (Main Log).")
@click.option("--email_address", type=str, multiple=True,
              help="The e-mail address to which the report should be sent.")
@click.option("--mail_server", type=str, cls=RequiredIf, required_if="email_address",
              help="The address of the e-mail SMTP server to use.")
@click.option("--mail_port", type=int, default=25, help="The port of the e-mail server. Defaults to 25")
@click.option("--mail_username", type=str, help="The username to authenticate with the e-mail server.")
@click.option("--mail_password", type=str, help="The password to authenticate with the e-mail server.")
def load_current_log_line(log_name_format, rivendell_host, sql_host, sql_user, sql_pass, sql_database_name, use_date,
                          use_time, dry_run, start_immediately, days_back, default_log, log_machine, email_address,
                          mail_server, mail_port, mail_username, mail_password):
    _logger.debug(f"With {locals()}")

    if email_address:
        emailer = wmul_emailer.EmailSender(
            server_host=mail_server,
            port=mail_port,
            user_name=mail_username,
            password=mail_password,
            destination_email_addresses=email_address,
            from_email_address='rivendell@wmul-nas-4'
        )
    else:
        emailer = None

    if use_date:
        use_date = use_date.date()
    else:
        use_date = datetime.datetime.now().date()

    if use_time:
        use_time = use_time.time()
    else:
        use_time = datetime.datetime.now().time()

    use_datetime = datetime.datetime.combine(date=use_date, time=use_time)

    x = LoadCurrentLogLineArguments(
        log_datetime=use_datetime,
        rivendell_host=rivendell_host,
        sql_host=sql_host,
        sql_user=sql_user,
        sql_pass=sql_pass,
        sql_database_name=sql_database_name,
        log_name_format=log_name_format,
        dry_run=dry_run,
        start_immediately=start_immediately,
        days_back=days_back,
        default_log=default_log,
        log_machine=log_machine,
        emailer=emailer
    )

    load_current_log_lines(x)


@wmul_rivendell_cli.command()
@click.argument('source_paths', type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True), nargs=-1)
@click.option('--cache_duration', type=int, default=180,
              help="How long (in seconds) this importer will remember a given file name after sending it to the "
                   "Rivendell importer. For this duration, this importer will ignore any other files with this name. "
                   "Defaults to 180 seconds (3 minutes).")
@click.option('--rdimport_syslog', is_flag=True, cls=MXWith, mx_with='rdimport_log_file_name',
              help="Tell rdimport to log to syslog.")
@click.option('--rdimport_log_file_name',
              type=click.Path(file_okay=True, dir_okay=False, readable=True, writable=True), cls=MXWith,
              mx_with="rdimport_syslog",  help="Tell rdimport to log to this filename.")
def import_with_file_system_metadata(source_paths, cache_duration, rdimport_syslog, rdimport_log_file_name):
    _logger.debug(f"With {locals()}")
    source_paths = [Path(sp) for sp in source_paths]

    if rdimport_log_file_name:
        rdimport_log_file_name = str(rdimport_log_file_name)
    else:
        rdimport_log_file_name = ""

    args = ImportRivendellFileWithFileSystemMetadataArguments(
        source_paths=source_paths,
        cache_duration=cache_duration,
        rdimport_syslog=rdimport_syslog,
        rdimport_log_file_name=rdimport_log_file_name
    )
    try:
        import_rivendell_file(arguments=args)
    except Exception as e:
        _logger.exception(f"Final crash: {e}")


def get_items_from_file(file_name):
    items = []
    if file_name:
        with open(file_name, "rt") as file_reader:
            for item in file_reader:
                trimmed_item = item.strip(" \n\r")
                if trimmed_item:
                    items.append(trimmed_item)
        if not items:
            raise ValueError(f"The file: {file_name}, did not contain any items. It appears to be blank or empty.")
    return items


def convert_cart_database(rivendell_cart_filename, output_filename, desired_fields_filename, include_macros, 
                          include_all_cuts, excluded_groups_file_name, converter):
    desired_fields = get_items_from_file(file_name=desired_fields_filename)
    excluded_groups = get_items_from_file(file_name=excluded_groups_file_name)
    output_filename = Path(output_filename)

    lcdd = LoadCartDataDump(
        rivendell_cart_data_filename=rivendell_cart_filename,
        include_all_cuts=include_all_cuts,
        include_macros=include_macros,
        excluded_group_list=excluded_groups
    )

    rivendell_carts = lcdd.load_carts()

    x = converter(
        rivendell_carts=rivendell_carts,
        desired_field_list=desired_fields,
        output_filename=output_filename
    )
    x.run_script()