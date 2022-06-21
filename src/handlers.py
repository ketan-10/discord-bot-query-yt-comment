from types import coroutine
import scrapetube
import contextlib
import asyncio
from youtube_dl import std_headers, YoutubeDL
from db import get_client
from io import StringIO
import webvtt
import re
import datetime
from pymongo.collection import Collection
from typing import TypedDict
import aiohttp


class ReturnedStatus(TypedDict):
    success: bool
    message: str


@contextlib.contextmanager
def get_youtube_dl():
    youtube_dl_options = {
        'skip_download': True,
        'ignoreerrors': True,
    }
    with YoutubeDL(youtube_dl_options) as ydl:
        yield ydl


def get_channel_meta_collection() -> Collection:
    client = get_client()
    database = client.get_database("channel-meta-db")
    collection = database.get_collection("channel-meta-collection")
    return collection


def getSubtitleUrl(video_data):
    subtitles = video_data.get('subtitles', {}).get('en', [])
    subtitles = list(filter(lambda sub: sub['ext'] == 'vtt', subtitles))
    if not subtitles:
        return None
    return subtitles[0]['url']


def timestamp_to_secs(timestamp: str) -> int:
    if '.' in timestamp:
        timestamp = timestamp.split('.')[0]
    result = int(str((datetime.datetime.strptime(timestamp, '%H:%M:%S') -
                 datetime.datetime(1900, 1, 1)).total_seconds()).split('.')[0])
    return result


def clean_text(text: str) -> str:
    return re.sub(' +', ' ', re.sub('[^A-Za-z0-9 ]+', ' ', text.lower()))


async def add_video_data(ydl: YoutubeDL, session: aiohttp.ClientSession, video_id: str, channel_id: str) -> ReturnedStatus:
    try:
        video_data = ydl.extract_info(video_id)
        subtitle_url = getSubtitleUrl(video_data)
        if not subtitle_url:
            return {
                "success": False,
                "message": "No subtitles found"
            }

        try:
            async with session.get(subtitle_url, headers=std_headers) as response:
                text = await response.content.read()
                text = text.decode("utf-8")

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to get subtitles from {subtitle_url} {e}"
            }
        client = get_client()
        database = client.get_database(channel_id)
        video_collection = database.get_collection(video_id)
        blob = ''
        for vtt in webvtt.read_buffer(StringIO(text)):
            try:
                data = {
                    'start': timestamp_to_secs(vtt.start),
                    'end': timestamp_to_secs(vtt.end),
                    'text': vtt.text,
                    'blob-start': len(blob)
                }
                blob += clean_text(vtt.text)
                data['blob-end'] = len(blob)
                video_collection.insert_one(data)
            except:
                pass

        blob_collection = database.get_collection("blob")
        blob_collection.insert_one({
            'video_id': video_id,
            'blob': blob,
        })
        return {
            "success": True,
            "message": f"{video_id} added successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to add video {video_id} {e}"
        }


async def handle_add_channel(channel_id: str, channel_name: str) -> ReturnedStatus:
    channel_meta_collection = get_channel_meta_collection()

    # data limit
    if channel_meta_collection.estimated_document_count() > 50:
        return {
            "success": False,
            "message": "Already Too many channels"
        }

    # already exits or data conflit
    existing_channels = list(channel_meta_collection.find({"$or": [
        {
            "channel_id": {"$eq": channel_id}
        },
        {
            "channel_name": {"$eq": channel_name}
        }
    ]}))
    if len(existing_channels) > 0:
        return {
            "success": False,
            "message": "Failed to add channel. conflicting channel already exists. " + str(list(existing_channels)),
        }

    # Get all videos
    videos = scrapetube.get_channel(channel_id)
    with get_youtube_dl() as ydl:
        try:
            async with aiohttp.ClientSession() as session:
                allresponse = await asyncio.gather(*[add_video_data(ydl, session, video['videoId'], channel_id) for video in videos])
                failed_results = [
                    res for res in allresponse if not res["success"]]
                print(f" {len(failed_results)} failed to out of {len(allresponse)}")
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to add channel {channel_id} {e}"
            }
    # add channel
    channel_meta_collection.insert_one({
        "channel_id": channel_id,
        "channel_name": channel_name
    })
    return {
        "success": True,
        "message": f"{channel_id} added successfully"
    }


async def handle_search(query: str, channel_name: str) -> ReturnedStatus:

    channel_meta_collection = get_channel_meta_collection()
    existing_channel = list(channel_meta_collection.find({
        "channel_name": {"$eq": channel_name}
    }))
    if len(existing_channel) == 0:
        return {
            "success": False,
            "message": f"Channel {channel_name} does not exist"
        }
    
    channel_id = existing_channel[0]['channel_id']
    db_client = get_client()
    print(channel_id)
    database = db_client.get_database(channel_id)
    collection = database.get_collection("blob")
    query = clean_text(query)
    blob_result = list(collection.find(
        {'blob': {'$regex': rf'\b{query}\b'}}).allow_disk_use(True).limit(1))
    if len(blob_result) == 0:
        return {
            "success": False,
            "message": "No match found in the database for the query"
        }
    blob_result = blob_result[0]
    video_id = blob_result['video_id']
    match = re.search(rf'\b{query}\b', blob_result['blob'])
    if not match:
        return {
            "success": False,
            "message": "Regex not match with the database result"
        }

    blob_start = match.start()
    blob_end = match.end()

    video_collection = database.get_collection(video_id)
    start_position = list(video_collection.find(
        {'blob-start': {'$lte': blob_start}, 'blob-end': {'$gte': blob_start}}).allow_disk_use(True).limit(1))
    end_position = list(video_collection.find(
        {'blob-start': {'$lte': blob_end}, 'blob-end': {'$gte': blob_end}}).allow_disk_use(True).limit(1))

    if len(start_position) == 0 or len(end_position) == 0:
        return {
            "success": False,
            "message": "Not found the blob"
        }

    return {
        "success": True,
        "message": f"https://www.youtube.com/embed/{video_id}?start={start_position[0]['start']}&end={end_position[0]['end']}"
    }
