def alert_sound(alert_type: str):
    try:
        sounds = {
            "BUY":     [(800,200),(1000,200),(1200,400)],
            "PROFIT":  [(1000,150),(1200,150),(1500,400)],
            "LOSS":    [(500,600)],
            "WARNING": [(600,500)],
            "STARTUP": [(600,150),(800,150),(1000,150),(1200,300)],
            "JARVIS":  [(1000,100),(1200,100)],
        }
        if winsound:
            for freq, dur in sounds.get(alert_type, []):
                winsound.Beep(freq, dur)
    except Exception:
        pass

def desktop_notify(title: str, message: str):
    """Notifications are disabled on Linux server."""
    pass
