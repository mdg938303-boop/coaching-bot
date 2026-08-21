"""
utils/states.py
সব ConversationHandler-এর state constants একসাথে রাখা হয়েছে যাতে
নম্বর কনফ্লিক্ট না হয়।
"""
from itertools import count

_c = count()

# ---- Class management ----
CLASS_ADD_NAME = next(_c)
CLASS_ADD_SCHEDULE = next(_c)
CLASS_EDIT_NAME = next(_c)

# ---- Student management ----
STUDENT_ADD_CLASS = next(_c)
STUDENT_ADD_NAME = next(_c)
STUDENT_ADD_ROLL = next(_c)
STUDENT_ADD_GUARDIAN_PHONE = next(_c)
STUDENT_ADD_ADDRESS = next(_c)
STUDENT_ADD_ADMISSION_DATE = next(_c)
STUDENT_EDIT_FIELD_VALUE = next(_c)
STUDENT_SEARCH_QUERY = next(_c)

# ---- Teacher management ----
TEACHER_ADD_NAME = next(_c)
TEACHER_ADD_ID = next(_c)
TEACHER_ADD_CLASSES = next(_c)

# ---- Attendance ----
ATT_CHOOSE_CLASS = next(_c)
ATT_CHOOSE_DATE = next(_c)
ATT_MARKING = next(_c)
ATT_CUSTOM_DATE_INPUT = next(_c)

# ---- Guardian linking ----
GUARDIAN_LINK_CODE = next(_c)

# ---- Reports ----
REPORT_STUDENT_SEARCH = next(_c)
REPORT_CLASS_MONTH_CLASS = next(_c)
REPORT_CLASS_MONTH_MONTH = next(_c)

# ---- Broadcast ----
BROADCAST_MESSAGE = next(_c)

# ---- Fee management ----
STUDENT_ADD_FEE = next(_c)
FEE_PAY_CLASS = next(_c)
FEE_PAY_STUDENT = next(_c)
FEE_PAY_AMOUNT = next(_c)
FEE_PAY_MONTH = next(_c)
FEE_PAY_METHOD = next(_c)
FEE_EDIT_AMOUNT = next(_c)
FEE_REPORT_STUDENT_SEARCH = next(_c)

# generic cancel text
CANCEL_TEXT = "❌ Cancel"
