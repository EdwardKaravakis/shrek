#!/usr/bin/bash -f

# Returns the full list of file replicas for a given dataset.  There is
# no guarentee of uniqueness.
function get_file_list() {
    rucio list-file-replicas --pfns $1 | sed 's/file:\/\/localhost//g'
}

# Get the number of events in the (daq) event file
function get_number_of_events() {
    dpipe -s f -d n -i $1 | wc -l
}

function decode_raw_filename() {
  local filename=`basename $1 .evt` 
  local temp=( `echo $filename  | awk -F'[_-]' '{print $1 " " $2 " " $3 " " $4 " "}'` )
  echo ${temp[@]}
}

function decode_dst_vtx_filename() {
# /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/pileup/run0006/DST_VERTEX_sHijing_0_20fm_50kHz_bkg_0_20fm-0000000006-00000.root
#                                                                       1     2      3    4  5     6    7  8  9      10       11
  local filename=`basename $1 .evt` 
  local temp=( `echo $filename  | awk -F'[_-]' '{print $1 "_" $2 " " $3 " " $4 " " $5 " " $6 "_" $7 " " $8 "_" $9 " " $10 " " $11 }'` )
  echo ${temp[@]}
}

function decode_dst_calo_filename() {
# /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/pileup/run0006/DST_CALO_G4HIT_sHijing_0_20fm_50kHz_bkg_0_20fm-0000000006-00000.root
#                                                                       1    2    3     4     5  6    7     8  9  10      11       12
  local filename=`basename $1 .evt` 
  local temp=( `echo $filename  | awk -F'[_-]' '{print $1 "_" $2 "_" $3 " " $4 " " $5 " " $6 " " $7 "_" $8 " " $9 "_" $10 " " $11 " " $12 }'` )
  echo ${temp[@]}
}

function build_dst_list() {
  local path=$1
  local dst=$2
  local temp=( `find ${path} -type f -name $2 | sort` ) 
  if [ -z $3 ]; then
      echo "${temp[@]}:0:$3"
  else
      echo "${temp[@]}"
  fi
  echo $1 $2 $3
}


# Each file contains 1339883 events
runnumber=329
dataset=group.sphenix:mdc2.rawdata.junk.rhic2023-03-29.00000329
mcdataset=group.sphenix:mdc2.shijing_hepmc.fm_0_20.g4hits.run0006

# Get list of files in dataset into an array
array=$( get_file_list ${dataset} )
#mcarray=$( get_file_list ${mcdataset} )
#mcarray=( `ls /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/pileup/run0006/DST_CALO_G4HIT

mcarray=( `find /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/pileup/run0006/ -type f -name DST_CALO_G4HIT*-00101.root | sort` )
vxarray=( `find /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/pileup/run0006/ -type f -name DST_VERTEX*-00101.root | sort` )
bbarray=( `find /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/pileup/run0006/ -type f -name DST_BBC_G4HIT*-00101.root | sort` )
trarray=( `find /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/trkrhit/run0006/ -type f -name DST_TRKR_HIT*-00101.root | sort` )

#build_dst_list /sphenix/lustre01/sphnxpro/mdc2/shijing_hepmc/fm_0_20/pileup/run0006/ 'DST_BBC_G4HIT*' 10

# Create temp workspace
DIRECTORY=/tmp/run${runnumber} 
if [ -d "$DIRECTORY" ]; then
  rm -r ${DIRECTORY}
fi
mkdir ${DIRECTORY}

echo "Building sequence list"

for f in ${array}; do

   temp=( $( decode_raw_filename $f ) )

   pfn=$f             # physical file location
   stream=${temp[0]}  # filestream
   type=${temp[1]}    # junk
   run=${temp[2]}     # run
   seq=${temp[3]}     # sequence number   
   nevt=1339883       # total number of events in file

   # fake up a filelist (based on sequences
   echo RAW: $f ${nevt} >> /tmp/run${runnumber}/run${run}-seq${seq}.filelist

done
echo "... done building"

echo "Aggregating across sequences"

# Now fake an event range in each of these.  We need coverage for 50k MC events
for f in `ls /tmp/run${runnumber}/*.filelist`; do

    # strip the sequence out of this
    filename=`basename $f .filelist | sed 's/seq....-//g'` 
   
    #echo 1 130000   >> /tmp/run${runnumber}/$filename-1-130kevts.filelist
    cat $f          >> /tmp/run${runnumber}/$filename-1-130kevts.filelist

done

echo "... done aggregating"

rawlists=( `ls /tmp/run${runnumber}/*kevts.filelist` )

echo "Building the MC/RAW event lists"

# Each MC file begins a new filelist
count=0
index=0
for mc in ${mcarray[@]}; do

  filename=`basename ${mc} .root`

  # Corresponding vertex file (hopefully stays in sync)
  vxfilename=`basename ${vxarray[$index]} .root`
  vx=${vxarray[$index]}

  # Corresponding bbc file (...)
  bbfilename=`basename ${bbarray[$index]} .root`
  bb=${bbarray[$index]}

  # Corresponding tracker file (...)
  trfilename=`basename ${trarray[$index]} .root`
  tr=${trarray[$index]}

  index=$index+1

  #echo $mc $vx $bb

  evt_min=$(( 400*count ))
  evt_max=$(( 400*(count+1) ))

  echo RANGE: $evt_min $evt_max >> /tmp/run${runnumber}/${filename}.filelist
  echo MC:    ${mc} >> /tmp/run${runnumber}/${filename}.filelist
  echo VTX:   ${vx} >> /tmp/run${runnumber}/${filename}.filelist
  echo BBC:   ${bb} >> /tmp/run${runnumber}/${filename}.filelist
  echo TRKR:  ${tr} >> /tmp/run${runnumber}/${filename}.filelist

  echo RANGE: $evt_min $evt_max 
  echo MC:  ${mc} 
  echo VTX: ${vx} 

  rawfiles=`shuf -e -n1 ${rawlists[@]}`
  cat $rawfiles >> /tmp/run${runnumber}/${filename}.filelist   
  #ls -l $rawfiles
  
  # Only allow the first 80k events in the raw files...
  count=$(( (count+1)%200 ))
  #count=$(( count+1 ))
  
done

find /tmp/run${runnumber}/ -type f -name 'DST_CALO_G4HIT*.filelist' | sort > run${runnumber}.filelist

#ls /tmp/run${runnumber}/G4*.filelist > run${runnumber}.filelist

echo submitting workflows .......................
#shrek --no-pause --submit --tag calor-workflow   workflows/rhic2023.AuAu200.demo/runCalorChain.yaml       --runNumber=${runnumber} --filelist=run${runnumber}.filelist --build=ana.352 > calor-workflow.log
#shrek --no-pause --submit --tag global-workflow  workflows/rhic2023.AuAu200.demo/runGlobalChain.yaml      --runNumber=${runnumber} --filelist=run${runnumber}.filelist --build=ana.352 > global-workflow.log
shrek --no-pause --submit --tag tracker-workflow workflows/rhic2023.AuAu200.demo/runTrackerChainJob*.yaml --runNumber=${runnumber} --filelist=run${runnumber}.filelist --build=ana.352 > tracker-workflow.log
