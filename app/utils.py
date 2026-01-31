from datetime import datetime



def parse_time(time_str: str, date, tz):
   
    try:
        t = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        t = datetime.strptime(time_str, "%H:%M:%S").time()

    return tz.localize(datetime.combine(date, t))
