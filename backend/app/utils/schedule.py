from datetime import datetime, timezone, timedelta
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.market import Market

def calculate_is_open_by_schedule(operating_hours: dict, current_time: datetime) -> bool:
    """
    Evaluates whether the current_time falls within any interval in operating_hours.
    Supports ranges (e.g. 'Mon-Sat': '08:00-22:00') and lists (e.g. 'Sun': '09:00-19:00').
    """
    if not operating_hours:
        return True # Default to open if no schedule registered
        
    day_abbr = current_time.strftime("%a") # e.g. "Fri"
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_map = {day: idx for idx, day in enumerate(day_names)}
    
    current_day_idx = day_map.get(day_abbr)
    if current_day_idx is None:
        return True
        
    current_minutes = current_time.hour * 60 + current_time.minute
    
    for key, val in operating_hours.items():
        matched = False
        normalized_key = key.strip()
        if "-" in normalized_key:
            parts = normalized_key.split("-")
            if len(parts) == 2:
                start_day, end_day = parts[0].strip(), parts[1].strip()
                start_idx = day_map.get(start_day)
                end_idx = day_map.get(end_day)
                if start_idx is not None and end_idx is not None:
                    if start_idx <= end_idx:
                        matched = start_idx <= current_day_idx <= end_idx
                    else:
                        # Wrap-around range e.g. "Fri-Sun"
                        matched = current_day_idx >= start_idx or current_day_idx <= end_idx
        elif "," in normalized_key:
            days = [d.strip() for d in normalized_key.split(",")]
            matched = day_abbr in days
        else:
            matched = (normalized_key == day_abbr)
            
        if matched:
            if not val or str(val).lower().strip() == "closed":
                return False
            time_parts = str(val).split("-")
            if len(time_parts) == 2:
                try:
                    start_str, end_str = time_parts[0].strip(), time_parts[1].strip()
                    sh, sm = map(int, start_str.split(":"))
                    eh, em = map(int, end_str.split(":"))
                    start_minutes = sh * 60 + sm
                    end_minutes = eh * 60 + em
                    if start_minutes <= end_minutes:
                        if start_minutes <= current_minutes <= end_minutes:
                            return True
                    else:
                        # Overnight shift e.g. "22:00-04:00"
                        if current_minutes >= start_minutes or current_minutes <= end_minutes:
                            return True
                except ValueError:
                    pass
            
    return False

async def check_and_update_markets_schedule(db: AsyncSession, markets: List[Market]):
    """
    Checks each market in a list, checks Jordan local time (UTC+3), and dynamically 
    updates is_currently_open in DB if regular schedule changed or manual override expired at midnight.
    """
    jordan_tz = timezone(timedelta(hours=3))
    now_jordan = datetime.now(jordan_tz)
    current_date = now_jordan.date()
    
    updated_any = False
    for market in markets:
        if market.is_manual_override:
            if market.override_set_at:
                override_jordan = market.override_set_at.astimezone(jordan_tz)
                if override_jordan.date() != current_date:
                    # Reset manual override at midnight
                    market.is_manual_override = False
                    market.override_set_at = None
                    new_status = calculate_is_open_by_schedule(market.operating_hours, now_jordan)
                    if market.is_currently_open != new_status:
                        market.is_currently_open = new_status
                        updated_any = True
            else:
                # Safe reset if timestamp is missing
                market.is_manual_override = False
                new_status = calculate_is_open_by_schedule(market.operating_hours, now_jordan)
                if market.is_currently_open != new_status:
                    market.is_currently_open = new_status
                    updated_any = True
        else:
            # Automatic weekly schedule evaluation
            new_status = calculate_is_open_by_schedule(market.operating_hours, now_jordan)
            if market.is_currently_open != new_status:
                market.is_currently_open = new_status
                updated_any = True
                
    if updated_any:
        await db.commit()
