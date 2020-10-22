# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
import logging
import os

from flask import Flask, redirect, render_template, request, url_for, flash

from google.cloud import datastore
from google.cloud import storage
from google.cloud import vision


CLOUD_STORAGE_BUCKET = os.environ.get("CLOUD_STORAGE_BUCKET")


app = Flask(__name__)


def get_image_datastore(key):
    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()
    query = datastore_client.query(kind='pictures')

    first_key = datastore_client.key('pictures', key)
    # key_filter(key, op) translates to add_filter('__key__', op, key).
    query.key_filter(first_key, '=')
    result = query.fetch()
    # [END datastore_key_filter]
    
    print("\n" + str(key))
    
    return list(result)

@app.route("/")
def homepage():
    return render_template("homepage.html")

@app.route('/post/<string:post_id>')
def post(post_id):
    image_entity = get_image_datastore(post_id)
    print("_____")
    print(image_entity)
    print(image_entity[0]["blob_name"])
    return render_template("post.html", image_entity=image_entity)

@app.route('/edit/<string:post_id>')
def edit(post_id):
    image_entity = get_image_datastore(post_id)
    print(" ... of edit ...")
    return render_template("edit.html", image_entity=image_entity)

@app.route("/photo_album")
def photo_album():
    
    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Use the Cloud Datastore client to fetch information from Datastore about
    # each photo.
    query = datastore_client.query()
    image_entities = list(query.fetch())
    # Return a Jinja2 HTML template and pass in image_entities as a parameter.
    return render_template("photo_album.html", image_entities=image_entities)


def save_to_cloud_storage(photo):
    # Create a Cloud Storage client.
    storage_client = storage.Client()

    # Get the bucket that the file will be uploaded to.
    bucket = storage_client.get_bucket(CLOUD_STORAGE_BUCKET)

    # Create a new blob and upload the file's content.
    blob = bucket.blob(photo.filename)
    blob.upload_from_string(photo.read(), content_type=photo.content_type)

    # Make the blob publicly viewable.
    blob.make_public()
    return blob

def call_vision_api(blob):
    # Create a Cloud Vision client.
    vision_client = vision.ImageAnnotatorClient()

    # Use the Cloud Vision client to label the uploaded image.
    source_uri = "gs://{}/{}".format(CLOUD_STORAGE_BUCKET, blob.name)
    image = vision.Image(source=vision.ImageSource(gcs_image_uri=source_uri))

    # Performs label detection on the image file
    response = vision_client.label_detection(image=image)
    if response.error.message:
        raise Exception(
            '{}\nFor more info on error messages, check: '
            'https://cloud.google.com/apis/design/errors'.format(
                response.error.message))

    return response.label_annotations


@app.route("/upload_photo", methods=["GET", "POST"])
def upload_photo():
    
    meta_data = {}
    # Receive user input data
    photo = request.files["file"]
    meta_data['name'] = request.form['name']
    meta_data['location'] = request.form['location']
    meta_data['date'] = request.form['date']
    
    blob =  save_to_cloud_storage(photo)

    labels = call_vision_api(blob)

    # category is used as the kind parametr for the new entity in Datastore
    category = label_classifier(labels)
    print(category)
    
    add_to_datastore(category, blob, meta_data)
    
    return render_template("homepage.html", labels=labels)

# Add an entity to the Google Datastore database associated with this project
def add_to_datastore(category, blob, meta_data):
    print("meta_data: ", str(meta_data))
    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Fetch the current date / time.
    current_datetime = datetime.now()

    # The kind for the new entity.
    kind = 'pictures'

    # The name/ID for the new entity.
    name = blob.name

    # Create the Cloud Datastore key for the new entity.
    key = datastore_client.key(kind, name)

    # Construct the new entity using the key. Set dictionary values for entity
    # keys blob_name, storage_public_url, timestamp, and joy.
    entity = datastore.Entity(key)
    entity["blob_name"] = blob.name
    entity["image_public_url"] = blob.public_url
    entity["timestamp"] = current_datetime
    entity["meta_data"] = meta_data
    entity["category"]  = category

    # Save the new entity to Datastore.
    datastore_client.put(entity)


# A simple function to figure out the category of the Google Vision API response label JSON
# into one of the 4 categories: People, Animals, Flowers or Other
def label_classifier(labels):
    
    animals = [
            "Mammal", "Bird","Insect", 
            "Insects", "Invertebrate", "Amphibian", 
            "reptile", "Fish","Mammal", 
            "Birds", "Invertebrates", "Amphibians",
            "Reptiles", "Carnivore", "Herbivore", "Omnivore"
            ]
    people = ["Face", "Skin", "Lip", "Hair", "Glasses", "Faces", 
                "Eye", "Eyes", "Hand", "Hands", "Foot", "Feet", "Head", "Nose"]
    flowers = ["Flowers", "Flower", "Plant", "Plants"]
    
    result = ""

    for label in labels:
        if label.description in animals:
            result = "Animals"
            break 
        elif label.description in people:
            result = "People"
            break 
        elif label.description in flowers:
            result = "Flowers"
            break
    
    if result:
        return result    
    else:
        return "Other"

        

@app.errorhandler(500)
def server_error(e):
    logging.exception("An error occurred during a request.")
    return (
        """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(
            e
        ),
        500,
    )


if __name__ == "__main__":
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
