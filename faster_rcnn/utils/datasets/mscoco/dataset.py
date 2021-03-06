from torchvision.datasets import CocoDetection
import os
import numpy as np
import logging
from torchvision import transforms
from PIL import Image
import torch

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CocoData(CocoDetection):
    def __init__(self,
                 root,
                 annFile,
                 data_name='train2014',
                 transform=None,
                 target_transform=None,
                 sorted_indexes=[]):
        super(CocoData, self).__init__(
            root, annFile, transform, target_transform)

        self._data_name = data_name
        self.sorted_indexes = sorted_indexes
        self.config = {'top_k': 2000,
                       'use_salt': True,
                       'cleanup': True,
                       'crowd_thresh': 0.7,
                       'min_size': 2}
        self.root = root
        cats = self.coco.loadCats(self.coco.getCatIds())
        self._classes = tuple(['__background__'] +
                              [cat['name'] for cat in cats])
        self._class_to_index = dict(
            zip(self.classes, xrange(len(self.classes))))
        self._class_to_coco_cat_id = dict(zip([c['name'] for c in cats],
                                              self.coco.getCatIds()))
        self._coco_cat_id_to_class_index = dict(
            [(self._class_to_coco_cat_id[class_name], self._class_to_index[class_name]) for class_name in self._classes[1:]])

        if transform is not None:
            self.transform = transform
        else:
            self.transform = lambda x: x

    @property
    def classes(self):
        return self._classes

    def _load_image_set_index(self):
        return self.coco.getImgIds()

    def __getitem__(self, index):
        """
        Args:
            index (int): Index
        Returns:
            tuple: (image, target) where target gt_boxes: (G, 5) vstack of [x1, y1, x2, y2, class]
        """
        coco = self.coco
        if len(self.sorted_indexes):
            img_id = self.ids[self.sorted_indexes[index]]
        else:
            img_id = self.ids[index]
        ann_id = coco.getAnnIds(imgIds=img_id, iscrowd=None)
        annotation = coco.loadAnns(ann_id)
        image_info = coco.loadImgs(img_id)[0]
        im_file_path = os.path.join(self.root, image_info['file_name'])
        width = image_info['width']
        height = image_info['height']
        # need to fixed

        img = Image.open(im_file_path).convert('RGB')
        origin_size = img.size

        img = self.transform(img)
        img = img.unsqueeze(0)
        target_size = tuple(img.size())
        im_info = np.array(
            [[float(target_size[2]), float(target_size[3]), 600. / min(origin_size)]])

        blobs = {}
        blobs['tensor'] = img
        # print img.shape
        # blobs['im_name'] = os.path.basename(im_file_path)
        # blobs['image_info'] = image_info

        # The standard in computer vision is to specify the top left corner and the bottom right corner.
        # The coordinates are parsed by <your_dataset.py> (for example coco.py)
        # in the function

        def bboxs(targets):
            for target in targets:
                overlap = np.array([0] * len(self.classes))
                x1 = np.max((0, target['bbox'][0]))
                y1 = np.max((0, target['bbox'][1]))
                x2 = np.min(
                    (width - 1, x1 + np.max((0, target['bbox'][2] - 1))))
                y2 = np.min(
                    (height - 1, y1 + np.max((0, target['bbox'][3] - 1))))
                class_index = self._coco_cat_id_to_class_index[target['category_id']]
                if target['iscrowd']:
                    overlap[:] = -1.0
                else:
                    overlap[class_index] = 1.0
                if target['area'] > 0 and x2 >= x1 and y2 >= y1:
                    yield [x1, y1, x2, y2], class_index
        try:
            gt_boxes, gt_classes = zip(
                *[box for box in bboxs(annotation)])
        except ValueError as e:
            logger.debug(str(e))
            return None

        gt_boxes = np.array(gt_boxes, dtype=np.uint16)
        gt_classes = np.array(gt_classes, dtype=np.int32)

        blobs['gt_classes'] = torch.from_numpy(gt_classes)
        blobs['boxes'] = torch.from_numpy(gt_boxes * im_info[0][2])
        blobs['im_info'] = torch.from_numpy(np.array(im_info, dtype=np.float32))
        blobs['im_name'] = image_info['file_name']
        return blobs
