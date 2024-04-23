import cv2
import numpy as np
import uuid
import logging
import utilitiesHelper  # Import utilities as helper functions
import time


class DeadReckoningTracker:
    """
    A class for tracking objects using dead reckoning in real-time video feeds.
    This tracker uses YOLO for object detection and applies dead reckoning to predict future object positions.

    Attributes:
    - model (YOLO): The YOLO object detection model.
    - cap (cv2.VideoCapture): Video capture object for frame acquisition.
    - file (file object): File object for logging detection data.
    - writer (csv.writer): CSV writer object for writing detection data.
    - alert_file (str): Path to the alert log file.
    - proximity_threshold (int): Distance threshold for proximity alerts.
    - start_time (float): Timestamp when tracking started.
    - last_positions (dict): Dictionary to store last known positions of objects for dead reckoning.
    - alert_times (list): List to store times when alerts were triggered.
    - label (str): Label for the detection area.
    - center_area (tuple): Coordinates for the central area of interest in the video frame.
    - predefined_image (np.array): Image to overlay on detection areas, if provided.

    Methods:
    - run(): Main loop to capture video frames and process detections.
    - process_detection(det, frame): Process each detection per frame using dead reckoning.
    - apply_dead_reckoning(det, timestamp): Apply dead reckoning to predict the object's future position.
    """

    def __init__(self, model_path, proximity_threshold, file_name_predict, file_name_alert, label_name, source=0, predefined_img_path=None):
        """
        Initializes the Dead Reckoning tracker with all necessary components and configurations, including
        an option for a predefined image overlay.

        Parameters:
        - model_path (str): Path to the YOLO model.
        - proximity_threshold (int): Proximity threshold in pixels for triggering alerts.
        - file_name_predict (str): Filename for the CSV file to log predictions.
        - file_name_alert (str): Filename for the CSV file to log alerts.
        - label_name (str): Label for the predefined image or detection area.
        - source (int, optional): Camera source or video file path. Defaults to 0.
        - predefined_img_path (str, optional): Path to an image for overlay purposes.
        """
        self.model = utilitiesHelper.load_model(model_path)
        self.cap = utilitiesHelper.initialize_video_capture(source)
        self.file, self.writer = utilitiesHelper.setup_csv_writer(file_name_predict)
        self.alert_file = file_name_alert
        self.proximity_threshold = proximity_threshold
        self.start_time = time.time()
        self.last_positions = {}
        self.alert_times = []
        self.label = label_name
        self.center_area = None
        self.predefined_image = cv2.imread(predefined_img_path) if predefined_img_path else None

    def run(self):
        """
        Main method to start the tracking process, including handling the predefined image if provided.
        Continuously captures frames, processes detections, and updates the UI until 'q' is pressed.
        """
        ret, frame = self.cap.read()  # Initial read to get frame dimensions
        if ret:
            self.center_area = utilitiesHelper.update_center_area(frame.shape[1], frame.shape[0], factor=2)
            if self.predefined_image is not None:
                # Resize predefined image to fit center area dimensions
                area_width = self.center_area[1][0] - self.center_area[0][0]
                area_height = self.center_area[1][1] - self.center_area[0][1]
                self.predefined_image = cv2.resize(self.predefined_image, (area_width, area_height))

        while ret:
            detections = utilitiesHelper.run_yolov8_inference(self.model, frame)
            for det in detections:
                self.process_detection(det, frame)
            frame = utilitiesHelper.highlight_center_area(frame, self.center_area, self.label, self.predefined_image)
            cv2.imshow("Frame", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            ret, frame = self.cap.read()

        utilitiesHelper.cleanup(self.cap, self.file)

    def process_detection(self, det, frame):
        """
        Processes each detection by applying dead reckoning based on previous positions and logs the data.

        Parameters:
        - det (list): Detection details including bounding box and class info.
        - frame (np.array): The current frame for drawing detections.
        """
        object_id = str(uuid.uuid4())
        color = utilitiesHelper.get_color_by_id(object_id)
        center_x, center_y, future_x, future_y = self.apply_dead_reckoning(det, time.time())
        utilitiesHelper.log_detection(self.writer, time.time(), center_x, center_y, future_x, future_y, det[6])
        utilitiesHelper.draw_predictions(frame, det, center_x, center_y, future_x, future_y, color)
        if utilitiesHelper.is_object_near(det, self.center_area, self.proximity_threshold):
            utilitiesHelper.trigger_proximity_alert()
            utilitiesHelper.handle_alert(self.alert_file, utilitiesHelper.save_alert_times, det, time.time(), center_x, center_y, future_x, future_y, self.start_time, self.center_area)

    def apply_dead_reckoning(self, det, timestamp):
        """
        Applies dead reckoning based on the object's last known and current positions to predict its future location.

        Parameters:
        - det (list): The detection data containing bounding box and class.
        - timestamp (float): The current time used for calculating movement speed.

        Returns:
        - tuple: Current and predicted future positions of the object (current_x, current_y, future_x, future_y).
        """
        x1, y1, x2, y2, _, cls, _ = det
        current_x = int((x1 + x2) / 2)
        current_y = int((y1 + y2) / 2)
        last_info = self.last_positions.get(cls, (current_x, current_y, timestamp))
        time_delta = timestamp - last_info[2]
        velocity_x = (current_x - last_info[0]) / time_delta if time_delta > 0 else 0
        velocity_y = (current_y - last_info[1]) / time_delta if time_delta > 0 else 0
        future_x = int(current_x + velocity_x * time_delta)
        future_y = int(current_y + velocity_y * time_delta)
        self.last_positions[cls] = (current_x, current_y, timestamp)
        return current_x, current_y, future_x, future_y


if __name__ == "__main__":
    tracker = DeadReckoningTracker(
        'yolov8n.pt',
        source=0,
        proximity_threshold=40,
        file_name_predict='tracking_and_predictions_DR.csv',
        file_name_alert='alert_times_DR.csv',
        predefined_img_path='../data/8.jpg',
        label_name="robotic arm"
    )
    tracker.run()
