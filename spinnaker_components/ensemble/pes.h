/**
 * Ensemble - PES
 * -----------------
 * Functions to perform PES decoder learning
 * 
 * Authors:
 *   - James Knight <knightj@cs.man.ac.uk>
 * 
 * Copyright:
 *   - Advanced Processor Technologies, School of Computer Science,
 *      University of Manchester
 * 
 * \addtogroup ensemble
 * @{
 */


#ifndef __PES_H_
#define __PES_H_

// Common includes
#include "common-typedefs.h"
#include "input_filtering.h"

// Ensemble includes
#include "ensemble.h"

//----------------------------------
// Structs
//----------------------------------
// Structure containing parameters and state required for PES learning
typedef struct pes_parameters_t
{
  // Scalar learning rate used in PES decoder delta calculation
  value_t learning_rate;
  
  // Index of the modulatory input signal filter that contains error signal
  uint32_t error_sig_index;
  
  // Which row decoder to apply PES to starts at
  uint32_t decoder_row;

  // Index of the activity filter to extract input from
  // -1 if this learning rule should use unfiltered activity
  int32_t activity_filter_index;
} pes_parameters_t;

//----------------------------------
// External variables
//----------------------------------
extern uint32_t g_num_pes_learning_rules;
extern pes_parameters_t *g_pes_learning_rules;

//----------------------------------
// Inline functions
//----------------------------------
/**
* \brief When using non-filtered activity, applies PES to a spike vector
*/
void pes_apply(uint32_t n_populations, uint32_t n_neurons_total,
               const uint32_t *population_lengths, value_t *decoder,
               const uint32_t *spikes, const if_collection_t *modulatory_filters);

//----------------------------------
// Functions
//----------------------------------
/**
* \brief Copy in data controlling the PES learning 
* rule from the PES region of the Ensemble.
*/
bool pes_initialise(address_t address);


//void pes_step(const if_collection_t *modulatory_filters);

/** @} */

#endif  // __PES_H__