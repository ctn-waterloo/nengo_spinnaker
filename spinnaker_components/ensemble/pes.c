/*
 * Ensemble - Data
 *
 * Authors:
 *   - James Knight <knightj@cs.man.ac.uk>
 * 
 * Copyright:
 *   - Advanced Processor Technologies, School of Computer Science,
 *      University of Manchester
 *   - Computational Neuroscience Research Group, Centre for
 *      Theoretical Neuroscience, University of Waterloo
 * 
 */

#include "pes.h"
#include "filtered_activity.h"

#include <string.h>

//-----------------------------------------------------------------------------
// Global variables
//-----------------------------------------------------------------------------
uint32_t g_num_pes_learning_rules = 0;
pes_parameters_t *g_pes_learning_rules = NULL;

//-----------------------------------------------------------------------------
// Global functions
//-----------------------------------------------------------------------------
void pes_apply(uint32_t n_populations, uint32_t n_neurons_total,
               const uint32_t *population_lengths, value_t *decoder,
               const uint32_t *spikes, const if_collection_t *modulatory_filters)
{
  // Loop through all the learning rules
  for(uint32_t l = 0; l < g_num_pes_learning_rules; l++)
  {
    // If this learning rule operates on un-filtered activity and should, therefore be updated here
    const pes_parameters_t *params = &g_pes_learning_rules[l];
    if(params->activity_filter_index == -1)
    {
      // Extract input signal from filter's output
      const if_filter_t *error_sig = &modulatory_filters->filters[params->error_sig_index];
      const value_t *error_val = error_sig->output;

      // Get pointer to first row of decoder matrix that this learning rule modifies
      value_t *rule_decoder = &decoder[params->decoder_row * n_neurons_total];

      // For each population
      uint32_t decoder_col = 0;
      for (uint32_t p = 0; p < n_populations; p++)
      {
        // Get the number of neurons in this population
        uint32_t pop_length = population_lengths[p];

        // While we have neurons left to process
        while (pop_length)
        {
          // Determine how many neurons are in the next word of the spike vector.
          uint32_t n = (pop_length > 32) ? 32 : pop_length;

          // Load the next word of the spike vector
          uint32_t data = *(spikes++);

          // Include the contribution from each neuron
          while (n)  // While there are still neurons left
          {
            // Work out how many neurons we can skip
            // XXX: The GCC documentation claims that `__builtin_clz(0)` is
            // undefined, but the ARM instruction it uses is defined such that:
            // CLZ 0x00000000 is 32
            uint32_t skip = __builtin_clz(data);

            // If `skip` is NOT less than `n` then there are either no firing
            // neurons left in the word (`skip` == 32) or the first `1` in the word
            // is beyond the range of bits we care about anyway.
            if (skip < n)
            {
              // Skip until we reach the next neuron which fired
              decoder_col += skip;

              // Loop through output dimensions and apply PES learning
              value_t *neuron_decoder = &rule_decoder[decoder_col];
              for(uint d = 0; d < error_sig->size; d++, neuron_decoder += n_neurons_total)
              {
                *neuron_decoder -= (params->learning_rate * error_val[d]);
              }

              // Prepare to test the neuron after the one we just processed.
              decoder_col++;
              skip++;              // Also skip the neuron we just decoded
              pop_length -= skip;  // Reduce the number of neurons left
              n -= skip;           // and the number left in this word.
              data <<= skip;       // Shift out processed neurons
            }
            // Otherwise, if there are no neurons left in this word
            else
            {
              decoder_col += n; // Point at the decoder for the next neuron
              pop_length -= n;  // Reduce the number left in the population
              n = 0;            // No more neurons left to process
            }
          }
        }
      }
    }
  }
}
//-----------------------------------------------------------------------------
bool pes_initialise(address_t address)
{
  // Read number of PES learning rules that are configured
  g_num_pes_learning_rules = address[0];
  
  io_printf(IO_BUF, "PES learning: Num rules:%u\n", g_num_pes_learning_rules);
  
  if(g_num_pes_learning_rules > 0)
  {
    // Allocate memory
    MALLOC_FAIL_FALSE(g_pes_learning_rules,
                      g_num_pes_learning_rules * sizeof(pes_parameters_t));
    
    // Copy learning rules from region into new array
    memcpy(g_pes_learning_rules, &address[1], g_num_pes_learning_rules * sizeof(pes_parameters_t));
    
    // Display debug
    for(uint32_t l = 0; l < g_num_pes_learning_rules; l++)
    {
      const pes_parameters_t *parameters = &g_pes_learning_rules[l];
      io_printf(IO_BUF, "\tRule %u, Learning rate:%k, Error signal index:%u, Decoder row:%u, Activity filter index:%d\n",
               l, parameters->learning_rate, parameters->error_sig_index, parameters->decoder_row, parameters->activity_filter_index);
    }
  }
  return true;
}
//-----------------------------------------------------------------------------
/*void pes_step(const if_collection_t *modulatory_filters)
{
  // Loop through all the learning rules
  for(uint32_t l = 0; l < g_num_pes_learning_rules; l++)
  {
    // Extract filtered error signal vector indexed by learning rule
    const pes_parameters_t *parameters = &g_pes_learning_rules[l];

    // If this learning rule operates on filtered activity and should, therefore be updated here
    if(parameters->activity_filter_index != -1)
    {
      // Extract input signal from filter's output
      const if_filter_t *filtered_input = &modulatory_filters->filters[parameters->error_signal_filter_index];
      const value_t *filtered_error_signal = filtered_input->output;

      // Extract filtered activity vector indexed by learning rule
      const value_t *filtered_activity = g_filtered_activities[parameters->activity_filter_index];

      // Loop through neurons
      for(uint n = 0; n < g_ensemble.n_neurons; n++)
      {
        // Get this neuron's decoder vector
        value_t *decoder_vector = neuron_decoder_vector(n);

        // Loop through output dimensions and apply PES to decoder values offset by output offset
        for(uint d = 0; d < filtered_input->size; d++)
        {
          decoder_vector[d + parameters->decoder_output_offset] -= (parameters->learning_rate * filtered_activity[n] * filtered_error_signal[d]);
        }
      }
    }
  }
}*/