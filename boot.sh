#!/bin/sh
# this script is used to boot a Docker container

echo "I am Here.........starting while"
pip3 install -r requirements.txt

## for i in $(pip list -o | awk 'NR > 2 {print $1}'); do pip install -U $i; done

# while true; do
#     flask db upgrade
#     if [[ "$?" == "0" ]]; then
#         break
#     fi
#     echo Deploy command failed, retrying in 5 secs...
#     sleep 5
# done


echo "I am Here.........DONE while"


exec gunicorn -b :5000 --access-logfile - --error-logfile - run:app
