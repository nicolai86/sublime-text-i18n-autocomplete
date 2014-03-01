#/usr/bin/env ruby
require "yaml"

class FlattenYaml
  attr_reader :keys
  def initialize
    @keys = []
  end

  def merge file
    yaml = YAML.load_file file
    @keys |= construct_keys(yaml.values[0])
  end

  def to_json
    @keys
  end

  protected

  def construct_keys yaml

    yaml.inject([]) do |keys, (key, value)|
      if value.is_a? Hash
        keys |= construct_keys(value).map { |child| "#{key}.#{child}" }
      else
        keys << "#{key}"
      end
    end
  end
end

flattener = FlattenYaml.new

Dir[ARGV[0] + "/**/*.yml"].each do |dir|
  flattener.merge(dir)
end

$stdout << flattener.to_json