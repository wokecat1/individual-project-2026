__app_name__ = "Algorithmic Stock Trading Simulator"
__version__ = "1.0"

(
    SUCCESS,
    DIR_ERROR,
    FILE_ERROR,
    DB_CONN_ERROR,
    DB_READ_ERROR,
    DB_WRITE_ERROR,
    INPUT_ERROR
) = range(7)

ERRORS = {
    DIR_ERROR: "config directory error",
    FILE_ERROR: "config file error",
    DB_CONN_ERROR: "database connection error",
    DB_READ_ERROR: "database read error",
    DB_WRITE_ERROR: "database write error",
    INPUT_ERROR: "user input error",
}

