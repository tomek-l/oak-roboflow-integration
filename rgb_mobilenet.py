import time
from pathlib import Path

import cv2
import depthai as dai
import numpy as np

from roboflow import RoboflowUploader

BLOB_PATH = "mobilenet-ssd_openvino_2021.4_6shave.blob"
LABELS = [
    "background",
    "aeroplane",
    "bicycle",
    "bird",
    "boat",
    "bottle",
    "bus",
    "car",
    "cat",
    "chair",
    "cow",
    "diningtable",
    "dog",
    "horse",
    "motorbike",
    "person",
    "pottedplant",
    "sheep",
    "sofa",
    "train",
    "tvmonitor",
]


def make_pipeline():
    # Pipeline
    pipeline = dai.Pipeline()

    # Camera
    camRgb = pipeline.create(dai.node.ColorCamera)
    camRgb.setPreviewSize(300, 300)
    camRgb.setInterleaved(False)
    camRgb.setFps(40)

    # Detector
    nn = pipeline.create(dai.node.MobileNetDetectionNetwork)
    nn.setConfidenceThreshold(0.5)
    nn.setBlobPath(BLOB_PATH)
    nn.setNumInferenceThreads(2)
    nn.input.setBlocking(False)

    # Image output
    xoutRgb = pipeline.create(dai.node.XLinkOut)
    xoutRgb.setStreamName("rgb")

    # Detection output
    nnOut = pipeline.create(dai.node.XLinkOut)
    nnOut.setStreamName("nn")

    # Link elements
    nn.passthrough.link(xoutRgb.input)
    camRgb.preview.link(nn.input)
    nn.out.link(nnOut.input)

    return pipeline


def parse_dets(detections, confidence_thr=0.9):

    labels = [LABELS[d.label] for d in detections if d.confidence > confidence_thr]

    bboxes = [
        [300 * d.xmin, 300 * d.ymin, 300 * d.xmax, 300 * d.ymax]
        for d in detections
        if d.confidence > confidence_thr
    ]

    # bboxes = np.rint(bboxes).astype(int)

    return labels, bboxes


# nn data (bounding box locations) are in <0..1> range - they need to be normalized with frame width/height
def frameNorm(frame, bbox):
    normVals = np.full(len(bbox), frame.shape[0])
    normVals[::2] = frame.shape[1]
    return (np.clip(np.array(bbox), 0, 1) * normVals).astype(int)


def overlay_boxes(frame, detections):

    frame = frame.copy()

    color = (255, 0, 0)
    for detection in detections:
        bbox = frameNorm(
            frame, (detection.xmin, detection.ymin, detection.xmax, detection.ymax)
        )
        cv2.putText(
            frame,
            LABELS[detection.label],
            (bbox[0] + 10, bbox[1] + 20),
            cv2.FONT_HERSHEY_TRIPLEX,
            0.5,
            color,
        )
        cv2.putText(
            frame,
            f"{int(detection.confidence * 100)}%",
            (bbox[0] + 10, bbox[1] + 40),
            cv2.FONT_HERSHEY_TRIPLEX,
            0.5,
            color,
        )
        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)

    return frame


def upload_all(frame: np.ndarray, labels: list, bboxes: list, fname: str):
    # Uploads `frame` as an image to Roboflow and saves it under `fname`.jpg
    # Then, upload annotations  with corresponding `bboxes` and `frame`

    # Upload image frame. Retreive Roboflow's image_id
    img_id = uploader.upload_image(frame, fname)

    # Annotate the image we just uploaded
    uploader.upload_annotation(img_id, fname=fname, labels=labels, bboxes=bboxes)


if __name__ == "__main__":

    # Initialize variables
    frame = None
    detections = []
    WHITE = (255, 255, 255)

    uploader = RoboflowUploader(
        dataset_name="oak-dataset2", api_key="vkIkZac3CXvp0RZ31B3f"
    )

    pipeline = make_pipeline()

    with dai.Device(pipeline) as device:

        qRgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
        qDet = device.getOutputQueue(name="nn", maxSize=4, blocking=False)

        while True:

            inRgb = qRgb.get()
            inDet = qDet.get()

            if inRgb is None or inDet is None:
                continue  # queue not ready, skip iteration

            frame = inRgb.getCvFrame()
            detections = inDet.detections

            # Display results
            frame_with_boxes = overlay_boxes(frame, detections)
            cv2.imshow("Roboflow Demo", frame_with_boxes)

            # Handle user input
            # Enter -> upload to Roboflow
            # q -> exit
            key = cv2.waitKey(1)
            if key == ord("q"):
                exit()
            elif key == 13:
                labels, bboxes = parse_dets(detections, confidence_thr=0.9)
                upload_all(frame, labels, bboxes, fname=int(1000 * time.time()))
