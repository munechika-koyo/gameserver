import json
import uuid
from enum import IntEnum
from sqlite3 import OperationalError

# from tkinter.messagebox import NO
from typing import Optional

# from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound
from sqlalchemy.future import Connection

from .db import engine


class InvalidToken(Exception):
    """指定されたtokenが不正だったときに投げる"""


class SafeUser(BaseModel):
    """token を含まないUser"""

    id: int
    name: str
    leader_card_id: int

    class Config:
        orm_mode = True


def create_user(name: str, leader_card_id: int) -> str:
    """Create new user and returns their token

    Parameters
    ----------
    name
        user name
    leader_card_id
        user card leader id
    """
    token = str(uuid.uuid4())
    # TODO: tokenが衝突したらリトライする必要がある.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user("
                "  name,"
                "  token,"
                "  leader_card_id"
                ")"
                "VALUES("
                "  :name,"
                "  :token,"
                "  :leader_card_id"
                ")"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
    return token


def _get_user_by_token(conn: Connection, token: str) -> Optional[SafeUser]:
    result = conn.execute(
        text("SELECT * FROM user WHERE token = :token"), {"token": token}
    )
    try:
        row = result.one()
    except NoResultFound:
        return None
    return SafeUser.from_orm(row)


def get_user_by_token(token: str) -> Optional[SafeUser]:
    """Retreive SafeUser obj from token

    Parameters
    ----------
    token
        user token

    Returns
    -------
        SafeUser object
    """
    with engine.begin() as conn:
        return _get_user_by_token(conn, token)


def update_user(
    token: str, name: Optional[str] = None, leader_card_id: Optional[int] = None
) -> None:
    """Update user info through parameters.

    Parameters
    ----------
    token
        user token
    name
        user name
    leader_card_id
        user card id
    """
    user = get_user_by_token(token)
    if user is None:
        return None

    # set values if a parameter is None
    if name is None:
        name = user.name
    if leader_card_id is None:
        leader_card_id = user.leader_card_id

    # execute below only if updating at least one parameter.
    if name != user.name or leader_card_id != user.leader_card_id:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE"
                    "  user "
                    "SET"
                    "  name = :name,"
                    "  leader_card_id = :leader_card_id "
                    "WHERE"
                    "  token = :token"
                ),
                {"name": name, "leader_card_id": leader_card_id, "token": token},
            )


def show_all_user() -> list[tuple[int, str, str, int]]:
    """Show all users in user table.

    Returns
    -------
    list[tuple(int, str, str, int)]
        all of user table rows
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT * FROM user"),
        )
    return result.fetchall()


def get_user_all() -> list[SafeUser]:
    """Retrieve all user

    Returns
    -------
    list[SafeUser]
        SafeUser instances
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT * FROM user"),
        )
    users = []
    for row in result:
        users.append(SafeUser.from_orm(row))
    return users


def delete_user_by_token(token: str) -> None:
    """Delete a user by token

    Parameters
    ----------
    token
        user token
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE "
                "FROM"
                "  user "
                "WHERE"
                "  token = :token"
            ),
            {"token": token},
        )


# === Enum structures =========================================================
class LiveDifficulty(IntEnum):
    normal = 1
    hard = 2


class JoinRoomResult(IntEnum):
    Ok = 1  # 入場OK
    RoomFull = 2  # 満員
    Disbanded = 3  # 解散済み
    OtherError = 4  # その他エラー


class WaitRoomStatus(IntEnum):
    Waiting = 1  # ホストがライブ開始ボタン押すのを待っている
    LiveStart = 2  # ライブ画面遷移OK
    Dissolution = 3  # 解散された


# === Room Structures =========================================================
class RoomID(BaseModel):
    room_id: int  # 部屋識別子


class RoomInfo(BaseModel):
    room_id: int  # 部屋識別子
    live_id: int  # プレイ対象の楽曲識別子
    joined_user_count: int  # 部屋に入っている人数
    max_user_count: int  # 部屋の最大人数

    class Config:
        orm_mode = True


class RoomUser(BaseModel):
    user_id: int  # ユーザー識別子
    name: str  # ユーザー名
    leader_card_id: int  # 設定アバター
    select_difficulty: LiveDifficulty  # 選択難易度
    is_me: bool  # リクエスト投げたユーザーと同じか
    is_host: bool  # 部屋を立てた人か


class ResultUser(BaseModel):
    user_id: int  # ユーザー識別子
    judge_count_list: list[int]  # 各判定数（良い判定から昇順）
    score: int  # 獲得スコア

    class Config:
        orm_mode = True


# === room sql execution ======================================================
def create_room(live_id: int, select_difficulty: int, user_id: int) -> int:
    with engine.begin() as conn:
        res = conn.execute(
            text(
                # Create Room record
                "INSERT INTO room("
                "  live_id,"
                "  joined_user_count"
                ")"
                "VALUES("
                "  :live_id,"
                "  1"
                ");"
                # Extract room_id
                "SELECT"
                "  LAST_INSERT_ID()"
            ),
            {"live_id": live_id},
        )
        # created room id
        room_id = res.lastrowid

        # create new room_member
        conn.execute(
            text(
                "INSERT INTO room_member("
                "  room_id,"
                "  user_id,"
                "  select_difficulty,"
                "  is_host"
                ") VALUE(:room_id, :user_id, :select_difficulty, :is_host)"
            ),
            {
                "room_id": room_id,
                "user_id": user_id,
                "select_difficulty": select_difficulty,
                "is_host": 1,
            },
        )

    return room_id


def _get_room_status(room_id: int) -> WaitRoomStatus:
    """Get Room status which corresponds WaitRoomStatus"""
    with engine.begin() as conn:
        status = conn.execute(
            text(
                "SELECT"
                "  status "
                "FROM"
                "  room "
                "WHERE"
                "  room_id = :room_id"
            ),
            {"room_id": room_id},
        )
    return WaitRoomStatus(status.scalar_one())


def get_available_rooms_by_live_id(live_id: int) -> list[RoomInfo]:
    with engine.begin() as conn:
        if live_id == 0:
            result = conn.execute(
                text(
                    "SELECT"
                    "  * "
                    "FROM"
                    "  room "
                    "WHERE "
                    "joined_user_count < 4 "
                    "AND status = :status"
                ),
                {"status": int(WaitRoomStatus.Waiting)}
            )
        else:
            result = conn.execute(
                text(
                    "SELECT"
                    "  * "
                    "FROM"
                    "  room "
                    "WHERE"
                    "  live_id = :live_id "
                    "AND joined_user_count < 4 "
                    "AND status = :status"
                ), {"live_id": live_id, "status": int(WaitRoomStatus.Waiting)}
            )
    rooms = []
    for row in result:
        rooms.append(RoomInfo.from_orm(row))
    return rooms


def join_room(room_id: int, select_difficulty: int, user_id: int) -> JoinRoomResult:
    with engine.begin() as conn:
        # identify if room is or disbanded.
        status = _get_room_status(room_id)
        if status != WaitRoomStatus.Waiting:
            return JoinRoomResult.OtherError

        # update joined user count if room is not full.
        try:
            conn.execute(
                text(
                    "UPDATE"
                    "  room "
                    "SET"
                    "  joined_user_count = CASE"
                    "    WHEN joined_user_count < 4 THEN joined_user_count + 1"
                    "  END "
                    "WHERE"
                    "  room_id = :room_id"
                ),
                {"room_id": room_id},
            )
        except OperationalError:
            return JoinRoomResult.RoomFull

        # create new room_member
        conn.execute(
            text(
                "INSERT INTO room_member("
                "  room_id,"
                "  user_id,"
                "  select_difficulty,"
                "  is_host"
                ")  VALUE("
                "  :room_id,"
                "  :user_id,"
                "  :select_difficulty,"
                "  :is_host"
                ")"
            ),
            {
                "room_id": room_id,
                "user_id": user_id,
                "select_difficulty": select_difficulty,
                "is_host": 0,
            },
        )
    return JoinRoomResult.Ok


def wait_room(room_id: int, user_id: int) -> tuple[WaitRoomStatus, list[RoomUser]]:
    with engine.begin() as conn:
        # get room status
        status = _get_room_status(room_id)

        # get users in the room
        user_rows = conn.execute(
            text(
                "SELECT"
                "  rm.user_id,"
                "  u.name,"
                "  u.leader_card_id,"
                "  rm.select_difficulty,"
                "  rm.is_host "
                "FROM"
                "  room_member AS rm"
                "  JOIN"
                "    user AS u"
                "  ON  rm.user_id = u.id "
                "WHERE"
                "  rm.room_id = :room_id"
            ),
            {"room_id": room_id},
        )
    users = []
    for row in user_rows:
        users.append(
            RoomUser(
                user_id=row[0],
                name=row[1],
                leader_card_id=row[2],
                select_difficulty=row[3],
                is_me=user_id == row[0],
                is_host=row[4],
            )
        )
    return (status, users)


def start_room(room_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE"
                "  room "
                "SET"
                "  status = :status "
                "WHERE"
                "  room_id = :room_id"
            ),
            {"status": int(WaitRoomStatus.LiveStart), "room_id": room_id},
        )


def end_room(
    room_id: int, judge_count_list: list[int], score: int, user_id: int
) -> None:
    with engine.begin() as conn:
        # store room_member's score
        conn.execute(
            text(
                "UPDATE"
                "  room_member "
                "SET"
                "  score = :score,"
                "  judge = :judge "
                "WHERE"
                "  room_id = :room_id "
                "AND user_id = :user_id"
            ),
            {
                "score": score,
                "judge": json.dumps(judge_count_list),
                "room_id": room_id,
                "user_id": user_id,
            },
        )


def all_user_results(room_id: int) -> list[ResultUser]:
    with engine.begin() as conn:
        # return [] when all member finished
        scores = conn.execute(
            text(
                "SELECT"
                "  score "
                "FROM"
                "  room_member "
                "WHERE"
                "  room_id = :room_id"
            ),
            {"room_id": room_id},
        )
        for row in scores:
            if row[0] is None:
                return []

        # if room status is LiveStart
        res = conn.execute(
            text(
                "SELECT"
                "  user_id,"
                "  judge,"
                "  score "
                "FROM"
                "  room_member "
                "WHERE"
                "  room_id = :room_id"
            ),
            {"room_id": room_id},
        )
    results = []
    for row in res:
        if row[1] is not None:
            judge = json.loads(row[1])
        else:
            continue
        results.append(
            ResultUser(
                user_id=row[0], judge_count_list=judge, score=row[2]
            )
        )

    return results


def leave_room(room_id: int, user_id: int) -> None:
    with engine.begin() as conn:
        # reduce joined user count
        conn.execute(
            text(
                "UPDATE"
                "  room "
                "SET"
                "  joined_user_count = CASE"
                "    WHEN joined_user_count > 0 THEN joined_user_count - 1"
                "  END "
                "WHERE"
                "  room_id = :room_id;"
            ),
            {"room_id": room_id},
        )
        # change room status if host leaves
        res = conn.execute(
            text(
                "SELECT"
                "  is_host "
                "FROM"
                "  room_member "
                "WHERE"
                "  user_id = :user_id "
                "AND room_id = :room_id"
            ),
            {"user_id": user_id, "room_id": room_id},
        )
        if res.scalar_one():
            conn.execute(
                text(
                    "UPDATE"
                    "  room "
                    "SET"
                    "  status = :status "
                    "WHERE"
                    "  room_id = :room_id"
                ),
                {"room_id": room_id, "status": int(WaitRoomStatus.Dissolution)},
            )
        # delete record from room_member
        conn.execute(
            text(
                "DELETE "
                "FROM"
                "  room_member "
                "WHERE"
                "  user_id = :user_id"
            ),
            {"user_id": user_id},
        )
