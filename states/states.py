from aiogram.fsm.state import State, StatesGroup


class BookingState(StatesGroup):
    service = State()
    date = State()
    time = State()
    comment = State()
    confirm = State()


class RescheduleState(StatesGroup):
    appointment = State()
    date = State()
    time = State()
    confirm = State()


class WaitingState(StatesGroup):
    service = State()
    date = State()


class ReviewState(StatesGroup):
    rating = State()
    text = State()


class AdminBlockState(StatesGroup):
    date = State()
    start = State()
    end = State()
    reason = State()
    confirm = State()


class AdminServiceState(StatesGroup):
    name = State()
    price = State()
    duration = State()
    edit_value = State()


class AdminBlacklistState(StatesGroup):
    user_id = State()
    reason = State()
