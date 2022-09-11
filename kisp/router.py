import os 
import binascii
import time 
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from fastapi import File, Form, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
from enum import Enum
from typing import List

import logging
import logging.handlers
# default logging settings, will be override by config file
logging.basicConfig(filename='server.log', filemode='w', level=logging.DEBUG)

router = APIRouter()

@router.get("/alive", response_class=PlainTextResponse, tags=["generic"], 
    description="Return true if service is up and running.")
def is_alive_status():
    return "true"

@router.get("/version", response_class=PlainTextResponse, tags=["generic"], 
    description="Return the version tag of the service.")
def get_version():
    api_settings = scorer.config['api']
    return api_settings['version']

from kisp.users_manager import fastapi_users
from kisp.db import User
current_superuser = fastapi_users.current_user(active=True, superuser=True)
current_user = fastapi_users.current_user(active=True)

@router.get("/users", tags=["users"],
    description="Return the list of available users.")
async def get_users(user: User = Depends(current_superuser)):
    start_time = time.time()
    result = {}
    result['count'] = 1
    from utils_db import get_items
    records = await get_items("user", {})
    result['records'] = records
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/tasks", tags=["tasks"],
    description="Return the list of available tasks.")
async def get_tasks():
    start_time = time.time()
    result = {}
    result['count'] = 1
    from utils_db import get_items
    records = await get_items("task", {})
    result['records'] = records
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/tasks/{identifier}", tags=["tasks"], 
    description="Return a task by its id")
async def get_task(identifier: str, user: User = Depends(current_user)):
    start_time = time.time()
    result = {}
    from utils_db import get_first_item
    item = await get_first_item("task", {"id": identifier})
    if item == None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    else:
        # enrich the task item with some additional information
        # dataset name
        dataset_item = await get_first_item("dataset", {"id": item["dataset_id"]})
        item["dataset_name"] = dataset_item["name"]

        # possible assigned user 
        from utils_db import get_assigned_user
        local_user = await get_assigned_user(identifier)
        if local_user == None or "user_id" not in local_user:
            item["status"] = "unassigned"
            item["assigned"] = None
        else:
            item["assigned"] = local_user["email"]
            item["status"] = "assigned"

        # number of documents, excerpts and annotations
        from utils_db import get_task_attributes
        task_attributes = await get_task_attributes(identifier, str(user.id))
        if "nb_documents" in task_attributes:
            item["nb_documents"] = task_attributes["nb_documents"]
        if "nb_excerpts" in task_attributes:
            item["nb_excerpts"] = task_attributes["nb_excerpts"]
        if "nb_pre_annotations" in task_attributes:
            item["nb_pre_annotations"] = task_attributes["nb_pre_annotations"]
        if "nb_completed_excerpts" in task_attributes:
            item["nb_completed_excerpts"] = task_attributes["nb_completed_excerpts"]

        result['record'] = item
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/tasks/{identifier}/excerpts", tags=["tasks"], 
    description="Return all excerpt identifiers from the given task")
async def get_task_excerpts(identifier: str):
    start_time = time.time()
    result = {}
    intask_dict = { "task_id": identifier }

    from utils_db import get_items
    items = await get_items("intask", intask_dict, full=True)
    if items == None or len(items)==0:
        raise HTTPException(status_code=404, detail="Excerpt not found")
    else:
        records = []
        for item in items:
            records.append(item["excerpt_id"])
        all_records = {}
        all_records["excerpts"] = records

        i = 0
        for item in items:
            local_annotation_dict = { "task_id": identifier, "excerpt_id": item["excerpt_id"], }
            local_annotations = await get_items("annotation", local_annotation_dict, full=True)
            excerptDone = False
            for local_annotation in local_annotations:
                if "user_id" in local_annotation and local_annotation["user_id"] != None:
                    excerptDone = True
                    continue

            if not excerptDone:
                all_records["first_non_complete"] = i
                break
            i += 1

        result["records"] = all_records

    result['runtime'] = round(time.time() - start_time, 3)
    return result   

@router.get("/tasks/{identifier}/excerpt", tags=["tasks"], 
    description="Return an excerpt from the given task")
async def get_task_excerpt(identifier: str, rank: int = None):
    '''
    To get an excerpt to be annotated or already annotated in task, parameter
    are its rank (in the task list of excerpts) or a jump method which can be:
    - "first": first in the task list (same as rank=0)
    - "last": last in the task list 
    '''
    start_time = time.time()
    result = {}
    intask_dict = { "task_id": identifier }

    if rank == -1 or rank == None:
        offset_from = 0
        offset_to = 1
    else: 
        offset_from = rank
        offset_to = rank+1

    from utils_db import get_items
    items = await get_items("intask", intask_dict, offset_from, offset_to, full=True)
    if items == None or len(items)==0:
        raise HTTPException(status_code=404, detail="Excerpt not found")
    else:
        # enrich the task item with some additional information
        # dataset name
        item = items[0]
        print(item)

        from utils_db import get_first_item
        excerpt_item = await get_first_item("excerpt", {"id": item["excerpt_id"]})
        if item == None:
            raise HTTPException(status_code=404, detail="Excerpt not found")
        else:
            result['record'] = excerpt_item
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/datasets", tags=["datasets"],
    description="Return the list of available datasets.")
async def get_datasets():
    start_time = time.time()
    result = {}
    result['count'] = 1
    from utils_db import get_items
    records = await get_items("dataset", {})
    result['records'] = records
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/datasets/{identifier}", tags=["datasets"], 
    description="Return a dataset by its id")
async def get_dataset(identifier: str):
    start_time = time.time()
    result = {}
    from utils_db import get_first_item
    item = await get_first_item("dataset", {"id": identifier})
    if item == None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    else:
        result['record'] = item
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/datasets/{identifier}/labels", tags=["datasets"], 
    description="Return the labels used in the dataset for a task type")
async def get_dataset_labels(identifier: str, type: str):
    start_time = time.time()
    result = {}
    from utils_db import get_items
    items = await get_items("label", {"dataset_id": identifier, "type": type}, full=True)
    if items == None or len(items)==0:
        raise HTTPException(status_code=404, detail="Labels not found")
    else:
        result['records'] = items
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.post("/tasks/{identifier}/assign", tags=["tasks"], 
    description="Assign a task to the current user")
async def post_self_assign_task(identifier: str, user: User = Depends(current_user)):
    start_time = time.time()
    result = {}
    from utils_db import get_first_item
    item = await get_first_item("task", { "id": identifier} )
    if item == None:
        raise HTTPException(status_code=400, detail="Task not found")
    else:
        assign_dict = { "task_id": identifier, "user_id": str(user.id), "in_progress": False, "completed_excerpts": 0 }
        from utils_db import insert_item
        assign_result = await insert_item("assign", assign_dict, add_id=False)
        if assign_result != None and "error" in assign_result:
            raise HTTPException(status_code=500, detail="Assignment failed: "+assign_result["error"])
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.post("/tasks/{identifier}/assign/{user_id}", tags=["tasks"], 
    description="Assign a task to an arbitrary given user")
async def post_assign_task(identifier: str, user_id: str, user: User = Depends(current_superuser)):
    start_time = time.time()
    result = {}
    from utils_db import get_first_item
    item = await get_first_item("task", {"id": identifier})
    if item == None:
        raise HTTPException(status_code=400, detail="Task not found")
    user = await get_user("user", user_id)
    if user == None:
        raise HTTPException(status_code=400, detail="User not found")
    assign_dict = {"task_id": identifier, "user_id": user_id }
    from utils_db import insert_item
    assign_result = await insert_item("assign", assign_dict, add_id=False)
    if assign_result != None and "error" in assign_result:
        raise HTTPException(status_code=400, detail="Assignment failed: "+assign_result["error"])
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.delete("/tasks/{identifier}/assign", tags=["tasks"], 
    description="Unassign a task from the current user")
async def post_self_unassign_task(identifier: str, user: User = Depends(current_user)):
    start_time = time.time()
    result = {}
    from utils_db import get_first_item
    item = await get_first_item("task", {"id": identifier})
    if item == None:
        raise HTTPException(status_code=400, detail="Task not found")
    else:
        assign_dict = { "task_id": identifier, "user_id": str(user.id) }
        from utils_db import delete_items
        assign_result = await delete_items("assign", assign_dict)
        if assign_result != None and "error" in assign_result:
            raise HTTPException(status_code=500, detail="Unassignment failed: "+assign_result["error"])
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.delete("/tasks/{identifier}/assign/{user_id}", tags=["tasks"], 
    description="Unassign a task from a given user")
async def post_assign_task(identifier: str, user_id: str, user: User = Depends(current_superuser)):
    start_time = time.time()
    result = {}
    from utils_db import get_first_item
    item = await get_first_item("task", {"id": identifier})
    if item == None:
        raise HTTPException(status_code=400, detail="Task not found")
    user = await get_user("user", user_id)
    if user == None:
        raise HTTPException(status_code=400, detail="User not found")
    assign_dict = {"task_id": identifier, "user_id": user_id }
    from utils_db import delete_items
    assign_result = await delete_items("assign", assign_dict)
    if assign_result != None and "error" in assign_result:
        raise HTTPException(status_code=500, detail="Unassignment failed: "+assign_result["error"])
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/annotations/{identifier}", tags=["annotations"], 
    description="Return an annotation by its id")
async def get_annotation(identifier: str):
    start_time = time.time()
    result = {}
    from utils_db import get_first_item
    item = await get_first_item("annotation", {"id": identifier})
    if item == None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    else:
        result['record'] = item
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.get("/annotations/excerpt/{identifier}", tags=["annotations"], 
    description="Return the annotations for a given excerpt, restricted to pre-annotations and current user annotations")
async def get_excerpt_annotation(identifier: str, type: str, user: User = Depends(current_user)):
    start_time = time.time()
    result = {}
    from utils_db import get_items
    items1 = await get_items("annotation", {"excerpt_id": identifier, "type": type, "user_id": str(user.id)}, full=True)
    items2 = await get_items("annotation", {"excerpt_id": identifier, "type": type, "user_id": None}, full=True)

    if items1 == None and items2 == None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    else:
        items = items1+items2
        result['records'] = items
    result['runtime'] = round(time.time() - start_time, 3)
    return result

@router.put("/annotations/annotation", tags=["annotations"], 
    description="Add or update an annotation")
async def add_annotation(request: Request, user: User = Depends(current_user)):
    start_time = time.time()
    result = {}

    annotation_dict = await request.json()

    # some validation here...
    annotation_dict["user_id"] = str(user.id)
    print(annotation_dict)

    # check if an annotation exists for this user, excerpt and task
    from utils_db import get_first_item

    dict_annot = {"user_id": annotation_dict["user_id"], "task_id": annotation_dict["task_id"], "excerpt_id": annotation_dict["excerpt_id"]}
    item = await get_first_item("annotation", dict_annot)
    if item == None:
        # we insert the new annotation
        from utils_db import insert_item
        annotation_result = await insert_item("annotation", annotation_dict, add_id=True)
        if annotation_result != None and "error" in annotation_result:
            raise HTTPException(status_code=500, detail="Annotation insert failed: "+annotation_result["error"])
        # keep track of progress at the task record
            
    else:
        # we update the existing annotation
        from utils_db import update_record
        annotation_result = await update_record("annotation", item["id"], annotation_dict)
        if annotation_result != None and "error" in annotation_result:
            raise HTTPException(status_code=500, detail="Annotation update failed: "+annotation_result["error"])

    if annotation_result != None and "id" in annotation_result:
        result["record"] = annotation_result["id"]
    else:
        result["record"] = None

    result['runtime'] = round(time.time() - start_time, 3)
    return result
