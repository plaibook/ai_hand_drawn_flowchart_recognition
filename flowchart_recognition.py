import os
from argparse import ArgumentParser
from json import dump
from math import sqrt
from operator import itemgetter
from sys import argv

import cv2
import numpy as np
from imutils import resize
from numpy.linalg import norm
from pytesseract import pytesseract
from tabulate import tabulate


def contour_circumstance(contour):
    temp, circumstance = contour[0], 0
    for point in contour[1:]:
        circumstance += sqrt((point[0][0] - temp[0][0]) ** 2 + (point[0][1] - temp[0][1]) ** 2)
        temp = point
    return circumstance


def distance(A, B, P):
    """ segment line AB, point P, where each one is an array([x, y]) """
    if np.arccos(np.dot((P - A) / norm(P - A), (B - A) / norm(B - A))) > np.pi / 2:
        return norm(P - A)
    if np.arccos(np.dot((P - B) / norm(P - B), (A - B) / norm(A - B))) > np.pi / 2:
        return norm(P - B)
    return norm(np.cross(A - B, A - P)) / norm(B - A)


def flowchart(filename, padding=25, offset=10, arrow=30, gui=True):
    img = cv2.imread(filename, 0)

    thresh = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 111, 48)
    cv2.imwrite('thresh.png', thresh)
    img = cv2.imread('thresh.png')

    image = img.copy()
    blur = cv2.GaussianBlur(image, (5, 5), 0)

    # resize the image
    resized = resize(blur, width=2 * image.shape[1])
    ratio = 0.5

    # convert the resized image to grayscale
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    # histogram
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    cl = clahe.apply(gray)

    denoised_cl = cv2.fastNlMeansDenoising(cl, None, 270, 7, 21)

    # Otsu's thresholding
    blur = cv2.GaussianBlur(denoised_cl, (25, 25), 0)

    _, thresh = cv2.threshold(blur, 10, 100, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # detect edges
    edge = cv2.Canny(thresh, 0, 255, apertureSize=3)

    # opening image for less noise
    blur = cv2.GaussianBlur(edge, (9, 9), 0)
    kernel = np.ones((3, 3), np.uint8)
    opening = cv2.morphologyEx(blur, cv2.MORPH_OPEN, kernel)

    # find contours in the thresholded image and initialize the shape detector
    contours, _ = cv2.findContours(opening.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # construct the list of bounding boxes
    boundingBoxes = [cv2.boundingRect(contour) for contour in contours]
    contours, boundingBoxes = zip(*sorted(zip(contours, boundingBoxes), key=lambda b: b[1][1], reverse=False))

    nodes, index, outside_texts, shapes, arrow_lines = {}, 1, {}, [], {}
    # loop over the contours
    for idx, contour in enumerate(contours):
        # compute the center of the contour, then detect the name of the shape using only the contour
        if len(contour) >= 5:
            area = cv2.contourArea(contour)
            _, (MA, ma), angle = cv2.fitEllipse(contour)
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)

            # (x,y) be the top-left coordinate of the rectangle and (w,h) be its width and height.
            x, y, w, h = cv2.boundingRect(approx)
            x = int(x * ratio)
            y = int(y * ratio)
            w = int(w * ratio)
            h = int(h * ratio)

            if (int(ma) < int(0.5 * resized.shape[0]) & int(MA) < int(0.5 * resized.shape[1])) or \
                    area > 0.001 * (image.shape[0] * image.shape[1]):
                M = cv2.moments(contour)
                cx = int((M["m10"] / (M["m00"])) * ratio)
                cy = int((M["m01"] / (M["m00"])) * ratio)

                circumstance = contour_circumstance(contour)

                if area / circumstance < 30:
                    shape = 'arrow'
                else:
                    perimeter = cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)

                    # if 3 vertices, triangle
                    if len(approx) == 3:
                        shape = "triangle"

                    # if 4 vertices, square
                    elif len(approx) == 4:
                        shape = "square"

                    # otherwise, we assume the shape is a circle
                    else:
                        shape = "circle"

                contour = contour.astype("float")
                contour *= ratio
                contour = contour.astype("int")

                if shape in ['square', 'circle', 'triangle']:
                    shapes.append(idx)

                    cropped = img.copy()
                    cv2.drawContours(cropped, [contour], -1, (255, 255, 255), padding)
                    cropped = cropped[y:y + h, x:x + w]
                    text = pytesseract.image_to_string(cropped)
                    if text == '':
                        position = 'Outside'
                    else:
                        position = 'Inside'

                    nodes[idx] = {
                        'Id': idx,
                        'Name': text,
                        'Position': position,
                        'Shape': shape,
                        'Line': []
                    }
                    index += 1
                else:
                    margin = 10
                    if y <= margin or x <= margin or y + h >= img.shape[1] - margin or x + w >= img.shape[0] - margin:
                        continue
                    text_offset = 5
                    cropped = img[y - text_offset:y + h + text_offset, x - text_offset:x + w + text_offset]
                    text = pytesseract.image_to_string(cropped)
                    if text != '':
                        shape = 'text'
                        outside_texts[idx] = text
                    else:
                        A, B, C, D = (x, y), (x, y + h), (x + w, y + h), (x + w, y)
                        start_point, end_point = None, None
                        for point in contour:
                            if point[0][0] < x + offset and point[0][1] < y + offset:
                                start_point = A
                                break
                            elif point[0][0] < x + offset and point[0][1] > y + h - offset:
                                start_point = B
                                break
                        if start_point is None:
                            start_point = A

                        for point in contour:
                            if point[0][0] > x + w - offset and point[0][1] > y + h - offset:
                                end_point = C
                                break
                            elif point[0][0] > x + w - offset and point[0][1] < y + offset:
                                end_point = D
                                break
                        if end_point is None:
                            end_point = C

                        start_contour_count, end_contour_count = 0, 0
                        for point in contour:
                            if (point[0][0] - start_point[0]) ** 2 + (point[0][1] - start_point[1]) ** 2 < arrow ** 2:
                                start_contour_count += 1
                            elif (point[0][0] - end_point[0]) ** 2 + (point[0][1] - end_point[1]) ** 2 < arrow ** 2:
                                end_contour_count += 1

                        if start_contour_count > end_contour_count:
                            reverse = True
                        else:
                            reverse = False
                        arrow_lines[idx] = (np.array(start_point), np.array(end_point), reverse)

                cv2.drawContours(image, [contour], -1, (0, 255, 0), 2)
                cv2.putText(
                    img=image, text=' '.join([str(idx), shape]), org=(cx + 10, cy - 20),
                    fontFace=cv2.FONT_HERSHEY_COMPLEX_SMALL, fontScale=1, color=(255, 0, 0), thickness=2
                )
                cv2.putText(
                    img=image, text=text, org=(cx + 10, cy + 40),
                    fontFace=cv2.FONT_HERSHEY_COMPLEX_SMALL, fontScale=1, color=(255, 0, 0), thickness=2
                )

    for node in nodes.keys():
        nodes[node]['Line'] = ', '.join(nodes[node]['Line'])
    nodes = list(nodes.values())
    print(tabulate(nodes, headers='keys'))

    filename = filename.replace('.jpg', '_out.jpg')
    filename = filename.replace('.png', '_out.png')
    cv2.imwrite(filename, image)
    with open('data.json', 'w') as file:
        dump({'Node': nodes}, file)

    # Save instead of showing image
    output_file = filename.replace(".png", "_processed.png").replace(".jpg", "_processed.jpg")
    cv2.imwrite(output_file, image)
    print(f"Processed image saved as {output_file}")

    try:
        os.remove("text.png")
    except:
        pass

    return nodes


if __name__ == '__main__':
    if len(argv) > 1:
        ap = ArgumentParser()

        ap.add_argument('-f', '--filename', required=True)
        ap.add_argument('-p', '--padding', type=int, default=25, required=False)
        ap.add_argument('-o', '--offset', type=int, default=10, required=False)
        ap.add_argument('-a', '--arrow', type=int, default=30, required=False)

        args = ap.parse_args()

        flowchart(**vars(args))
    else:
        input_file = input('image file: ')
        flowchart(filename=input_file)
